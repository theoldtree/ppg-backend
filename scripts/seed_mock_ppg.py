#!/usr/bin/env python3
"""
BUT-PPG → mock_ppg_sources / mock_ppg_packets DB seed script

각 BUT-PPG 레코딩의 정규화된 float 신호를 10-bit 정수로 변환하고,
12샘플씩 묶어 15바이트 BLE 패킷으로 팩킹하여 DB에 저장.

실행:
    cd /Users/yujeongmu/Desktop/ppg-backend
    python scripts/seed_mock_ppg.py

패킷 구조 (20 bytes total, only packet_bytes=15 stored):
  Sync(1B) + Index(2B) + PPG(15B: 12×10-bit) + Battery(1B) + CRC(1B)
  DB에는 PPG(15B)만 packet_bytes에 저장; sync/battery/crc는 별도 컬럼.
"""

import os, sys, struct, csv, json

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DATASET_DIR = "/Users/yujeongmu/Desktop/butppg-dataset/brno-university-of-technology-smartphone-ppg-database-but-ppg-2.0.0"
SAMPLES_PER_PACKET = 12       # 12 × 10-bit = 120-bit = 15 bytes
BITS_PER_SAMPLE    = 10
MAX_VAL_10BIT      = (1 << BITS_PER_SAMPLE) - 1  # 1023

# ── DB 설정 ──────────────────────────────────────────────────────────────────
from app.db.database import SessionLocal
from app.db.models.measurement import MockPPGSource, MockPPGPacket


# ─── BUT-PPG 신호 읽기 (build_mock_ppg.py 와 동일 로직) ──────────────────────

def read_ppg_signal(record_id: str) -> list[float] | None:
    hea_path = os.path.join(DATASET_DIR, record_id, f"{record_id}_PPG.hea")
    dat_path = os.path.join(DATASET_DIR, record_id, f"{record_id}_PPG.dat")
    if not os.path.exists(hea_path) or not os.path.exists(dat_path):
        return None

    with open(hea_path) as f:
        lines = f.readlines()

    header = lines[0].strip().split()
    n_sig  = int(header[1])
    n_samp = int(header[3]) if len(header) > 3 else 1

    sig_infos = []
    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        gs = parts[2]
        try:
            gain     = float(gs.split("(")[0])
            baseline = int(gs.split("(")[1].split(")")[0])
            sig_infos.append((gain, baseline))
        except Exception:
            continue

    with open(dat_path, "rb") as f:
        raw = f.read()
    total = len(raw) // 2
    if total == 0:
        return None
    raw_ints = struct.unpack(f"<{total}h", raw)

    # Format A: gain-encoded (300 channels × 1 sample)
    if n_samp == 1 and n_sig >= 100:
        if not sig_infos:
            return None
        return [(-b / g) for g, b in sig_infos]

    # Format B: interleaved (n_sig channels × 300 samples)
    if n_sig >= 1 and n_samp > 1 and sig_infos:
        g0, b0 = sig_infos[0]
        ch0 = raw_ints[0::n_sig]
        return [(v - b0) / g0 for v in ch0]

    return None


def normalize(signal: list[float]) -> list[float]:
    lo, hi = min(signal), max(signal)
    rng = hi - lo
    if rng < 1e-9:
        return [0.5] * len(signal)
    return [(v - lo) / rng for v in signal]


# ─── 10-bit 팩킹 ──────────────────────────────────────────────────────────────

def pack_12_samples(samples_float: list[float]) -> bytes:
    """12개 float (0~1) → 12 × 10-bit → 15 bytes (big-endian bit stream)"""
    assert len(samples_float) == SAMPLES_PER_PACKET
    bits = 0
    for v in samples_float:
        val = max(0, min(MAX_VAL_10BIT, round(v * MAX_VAL_10BIT)))
        bits = (bits << BITS_PER_SAMPLE) | val
    # 120 bits → 15 bytes
    result = []
    for i in range(14, -1, -1):
        result.append((bits >> (i * 8)) & 0xFF)
    return bytes(result)


def simple_crc(data: bytes) -> int:
    """XOR checksum over bytes"""
    crc = 0
    for b in data:
        crc ^= b
    return crc


# ─── 메인 ────────────────────────────────────────────────────────────────────

def load_quality_records() -> list[dict]:
    path = os.path.join(DATASET_DIR, "quality-hr-ann.csv")
    recs = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["Quality"] == "1":
                recs.append({"id": row["ID"], "hr_ref": float(row["HR"])})
    return recs


def detect_format(record_id: str) -> str | None:
    hea_path = os.path.join(DATASET_DIR, record_id, f"{record_id}_PPG.hea")
    if not os.path.exists(hea_path):
        return None
    with open(hea_path) as f:
        header = f.readline().strip().split()
    n_sig  = int(header[1])
    n_samp = int(header[3]) if len(header) > 3 else 1
    if n_samp == 1 and n_sig >= 100:
        return "A"
    if n_samp > 1:
        return "B"
    return None


def seed(max_sources: int = 50):
    quality_recs = load_quality_records()
    db = SessionLocal()

    try:
        inserted_sources = 0
        inserted_packets = 0

        for rec in quality_recs[:max_sources]:
            rid = rec["id"]

            # 이미 존재하면 건너뜀
            existing = db.query(MockPPGSource).filter_by(record_id=rid).first()
            if existing:
                print(f"  SKIP {rid} (already seeded)")
                continue

            signal = read_ppg_signal(rid)
            if signal is None or len(signal) < SAMPLES_PER_PACKET:
                print(f"  SKIP {rid} (signal read failed or too short)")
                continue

            norm = normalize(signal)
            fmt  = detect_format(rid)

            source = MockPPGSource(
                record_id=rid,
                hr_ref=rec["hr_ref"],
                quality=1,
                format=fmt,
            )
            db.add(source)
            db.flush()  # source.id 확보

            # 12샘플씩 패킷으로 분할
            packets = []
            n_full = len(norm) // SAMPLES_PER_PACKET
            for pkt_idx in range(n_full):
                chunk = norm[pkt_idx * SAMPLES_PER_PACKET:(pkt_idx + 1) * SAMPLES_PER_PACKET]
                packed = pack_12_samples(chunk)
                crc    = simple_crc(packed)
                packets.append(MockPPGPacket(
                    source_id    = source.id,
                    packet_index = pkt_idx,
                    sync_byte    = 0xAA,
                    packet_bytes = packed,
                    battery_level= 100,
                    crc          = crc,
                ))

            db.bulk_save_objects(packets)
            inserted_sources += 1
            inserted_packets  += len(packets)
            print(f"  OK  {rid}  HR={rec['hr_ref']}  fmt={fmt}  samples={len(norm)}  packets={len(packets)}")

        db.commit()
        print(f"\n완료: sources={inserted_sources}, packets={inserted_packets}")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed mock PPG data into DB")
    parser.add_argument("--max", type=int, default=50, help="Max number of sources to seed")
    args = parser.parse_args()
    print(f"BUT-PPG → DB 시딩 시작 (max={args.max})...")
    seed(args.max)
