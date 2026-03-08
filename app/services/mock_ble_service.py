"""
Mock BLE Service

실제 BLE 통신을 흉내 내어 MockPPGPacket 데이터를 패킷 단위로 언패킹하고,
QC → 분석 파이프라인을 그대로 통과시킨다.

패킷 구조 (20 bytes):
  Sync(1B) + Index(2B) + PPG(15B: 12 × 10-bit) + Bat(1B) + CRC(1B)
  DB에는 PPG(15B)가 packet_bytes에, sync/battery/crc는 별도 컬럼에 저장.
"""

from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.measurement import MockPPGSource, MockPPGPacket, Measurement, QCFeedback
from app.services.qc_service import analyze_ppg_signal

# ── 상수 ──────────────────────────────────────────────────────────────────────
SAMPLES_PER_PACKET = 12       # 패킷당 10-bit 샘플 수
BITS_PER_SAMPLE    = 10
MAX_VAL_10BIT      = (1 << BITS_PER_SAMPLE) - 1   # 1023
QC_WINDOW_SAMPLES  = 400      # QC 서비스가 요구하는 고정 샘플 수
MOCK_SAMPLING_RATE = 300      # BUT-PPG 데이터셋 샘플링 레이트 (Hz)


# ── 패킷 언패킹 ───────────────────────────────────────────────────────────────

def unpack_packet(packet_bytes: bytes) -> list[float]:
    """
    15 bytes (big-endian bit stream) → 12 × 10-bit 정수 → float 리스트 [0, 1023]

    pack_12_samples() 의 역연산:
      sample[0] → bits[119:110] (MSB)
      sample[11] → bits[9:0]   (LSB)
    """
    assert len(packet_bytes) == 15, f"패킷 길이 오류: {len(packet_bytes)} (expected 15)"
    bits = int.from_bytes(packet_bytes, "big")
    return [
        float((bits >> ((SAMPLES_PER_PACKET - 1 - i) * BITS_PER_SAMPLE)) & MAX_VAL_10BIT)
        for i in range(SAMPLES_PER_PACKET)
    ]


def validate_crc(packet_bytes: bytes, expected_crc: int) -> bool:
    """XOR 체크섬 검증"""
    crc = 0
    for b in packet_bytes:
        crc ^= b
    return crc == expected_crc


# ── BLE 시뮬레이션 메인 함수 ──────────────────────────────────────────────────

def simulate_ble_measurement(
    source_id: int,
    user_id: int,
    db: Session,
    is_dev: bool = True,
) -> dict:
    """
    MockPPGPacket 레코드를 순서대로 꺼내 실제 BLE 수신처럼 처리한다.

    1. DB에서 패킷 로드
    2. 각 패킷 언패킹 → 평탄 float 배열 구성
    3. 400 샘플 단위 QC 윈도우 처리 (QCFeedback 저장)
    4. Measurement 레코드 생성 & 완료 처리

    Returns:
        {
          "measurement": Measurement,
          "all_ppg_data": list[float],   # 전체 PPG (10-bit scale)
          "qc_results": list[dict],
          "battery_level": int,
          "sampling_rate": int,
        }
    """
    # ── 소스 및 패킷 조회 ─────────────────────────────────────────────────────
    source = db.query(MockPPGSource).filter(MockPPGSource.id == source_id).first()
    if not source:
        raise ValueError(f"MockPPGSource {source_id} 를 찾을 수 없습니다")

    packets: list[MockPPGPacket] = (
        db.query(MockPPGPacket)
        .filter(MockPPGPacket.source_id == source_id)
        .order_by(MockPPGPacket.packet_index)
        .all()
    )
    if not packets:
        raise ValueError(f"source_id={source_id} 에 저장된 패킷이 없습니다")

    # ── Measurement 레코드 생성 ────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    measurement = Measurement(
        user_id=user_id,
        mock_source_id=source_id,
        started_at=now,
        status="in_progress",
        is_dev=is_dev,
    )
    db.add(measurement)
    db.flush()  # measurement.id 확보

    # ── 패킷 언패킹 → 평탄 PPG 배열 ──────────────────────────────────────────
    all_ppg: list[float] = []
    battery_levels: list[int] = []

    for pkt in packets:
        # CRC 검증 (실패해도 계속 진행 — 실제 BLE처럼 경고만)
        if pkt.crc is not None and not validate_crc(pkt.packet_bytes, pkt.crc):
            pass  # 실제 장치에서도 재전송 없이 그냥 수신하는 시나리오

        samples = unpack_packet(pkt.packet_bytes)
        all_ppg.extend(samples)
        battery_levels.append(pkt.battery_level)

    # ── QC 윈도우 처리 (400 샘플 단위) ────────────────────────────────────────
    qc_results: list[dict] = []
    window_index = 0

    for start in range(0, len(all_ppg) - QC_WINDOW_SAMPLES + 1, QC_WINDOW_SAMPLES):
        window = all_ppg[start : start + QC_WINDOW_SAMPLES]
        timestamp = start / MOCK_SAMPLING_RATE

        qc_result = analyze_ppg_signal(window)
        db.add(QCFeedback(
            measurement_id=measurement.id,
            window_index=window_index,
            timestamp=timestamp,
            is_acceptable=qc_result["is_acceptable"],
            snr=qc_result["snr"],
            peak_count=qc_result["peak_count"],
            feedback_message=qc_result["feedback_message"],
        ))
        qc_results.append(qc_result)
        window_index += 1

    # ── Measurement 완료 처리 ─────────────────────────────────────────────────
    avg_battery = int(sum(battery_levels) / len(battery_levels)) if battery_levels else 100
    duration_sec = max(1, len(all_ppg) // MOCK_SAMPLING_RATE)

    measurement.completed_at = now
    measurement.status = "completed"
    measurement.duration_seconds = duration_sec

    db.commit()
    db.refresh(measurement)

    return {
        "measurement": measurement,
        "all_ppg_data": all_ppg,
        "qc_results": qc_results,
        "battery_level": avg_battery,
        "sampling_rate": MOCK_SAMPLING_RATE,
    }
