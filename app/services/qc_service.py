"""
PPG Signal Quality Control Service

Analyzes PPG signal quality and provides real-time feedback
"""
import numpy as np
from typing import Tuple, Optional


class PPGQualityControl:
    """
    Real-time PPG signal quality control
    """

    # Quality thresholds
    SNR_THRESHOLD = 5.0  # Minimum acceptable SNR
    MIN_PEAK_COUNT = 2   # Minimum peaks in 2-second window (~60 bpm)
    MAX_PEAK_COUNT = 8   # Maximum peaks in 2-second window (~240 bpm)
    MIN_DC_LEVEL = 30    # Minimum DC level (finger pressure)
    MAX_DC_LEVEL = 200   # Maximum DC level (too much pressure)
    MIN_AC_AMPLITUDE = 5 # Minimum AC amplitude
    MAX_VARIABILITY = 0.5 # Maximum coefficient of variation

    def __init__(self, sampling_rate: int = 200):
        """
        Initialize QC service

        Args:
            sampling_rate: Sampling rate in Hz (default 200Hz)
        """
        self.sampling_rate = sampling_rate

    def analyze_signal(self, ppg_data: list[float]) -> dict:
        """
        Analyze PPG signal quality and generate feedback

        Args:
            ppg_data: List of PPG values (should be 400 samples for 2-second window at 200Hz)

        Returns:
            dict with keys:
                - is_acceptable: bool
                - snr: float or None
                - peak_count: int or None
                - feedback_message: str
                - feedback_type: str (good/pressure/motion/coverage/weak)
        """
        if len(ppg_data) != 400:
            return {
                "is_acceptable": False,
                "snr": None,
                "peak_count": None,
                "feedback_message": f"데이터 길이 오류 (예상: 400, 실제: {len(ppg_data)})",
                "feedback_type": "error"
            }

        data = np.array(ppg_data, dtype=np.float64)

        # Calculate basic signal metrics
        dc_level = np.mean(data)
        ac_amplitude = np.std(data)
        signal_range = np.ptp(data)

        # Calculate SNR
        snr = self._calculate_snr(data)

        # Detect peaks
        peak_count = self._detect_peaks(data)

        # Calculate signal variability (motion artifact indicator)
        variability = self._calculate_variability(data)

        # Determine quality and generate feedback
        return self._generate_feedback(
            dc_level=dc_level,
            ac_amplitude=ac_amplitude,
            signal_range=signal_range,
            snr=snr,
            peak_count=peak_count,
            variability=variability
        )

    def _calculate_snr(self, data: np.ndarray) -> float:
        """
        Calculate Signal-to-Noise Ratio

        Simple SNR = AC component / high-frequency noise
        """
        # Detrend signal
        detrended = data - np.mean(data)

        # Apply simple moving average to get signal
        window_size = 10
        signal = np.convolve(detrended, np.ones(window_size)/window_size, mode='valid')

        # Calculate noise (high frequency component)
        noise = detrended[:len(signal)] - signal

        # SNR = signal power / noise power
        signal_power = np.mean(signal ** 2)
        noise_power = np.mean(noise ** 2)

        if noise_power < 1e-10:  # Avoid division by zero
            return 100.0

        snr = 10 * np.log10(signal_power / noise_power)
        return float(snr)

    def _detect_peaks(self, data: np.ndarray) -> int:
        """
        Simple peak detection for heart rate estimation

        Returns number of peaks detected in the signal
        """
        # Detrend
        detrended = data - np.mean(data)

        # Simple threshold-based peak detection
        threshold = np.std(detrended) * 0.5

        peaks = []
        for i in range(1, len(detrended) - 1):
            if (detrended[i] > threshold and
                detrended[i] > detrended[i-1] and
                detrended[i] > detrended[i+1]):
                # Check if not too close to previous peak (min 0.3 sec apart)
                if not peaks or (i - peaks[-1]) > int(0.3 * self.sampling_rate):
                    peaks.append(i)

        return len(peaks)

    def _calculate_variability(self, data: np.ndarray) -> float:
        """
        Calculate coefficient of variation
        High variability may indicate motion artifacts
        """
        mean_val = np.mean(data)
        std_val = np.std(data)

        if mean_val < 1e-10:
            return 1.0

        return std_val / mean_val

    def _generate_feedback(
        self,
        dc_level: float,
        ac_amplitude: float,
        signal_range: float,
        snr: float,
        peak_count: int,
        variability: float
    ) -> dict:
        """
        Generate user-friendly feedback based on signal metrics

        Priority order:
        1. Finger placement/coverage (DC level too low)
        2. Excessive pressure (DC level too high)
        3. Motion artifacts (high variability)
        4. Weak signal (low AC amplitude)
        5. Heart rate out of range
        6. Good signal
        """

        # Check finger coverage/placement (highest priority)
        if dc_level < self.MIN_DC_LEVEL:
            return {
                "is_acceptable": False,
                "snr": snr,
                "peak_count": peak_count,
                "feedback_message": "센서를 손가락으로 완전히 덮어주세요",
                "feedback_type": "coverage"
            }

        # Check excessive pressure
        if dc_level > self.MAX_DC_LEVEL:
            return {
                "is_acceptable": False,
                "snr": snr,
                "peak_count": peak_count,
                "feedback_message": "손가락 압력을 줄여주세요",
                "feedback_type": "pressure_high"
            }

        # Check motion artifacts (high variability with low SNR)
        if variability > self.MAX_VARIABILITY and snr < self.SNR_THRESHOLD:
            return {
                "is_acceptable": False,
                "snr": snr,
                "peak_count": peak_count,
                "feedback_message": "손가락을 움직이지 말고 가만히 있어주세요",
                "feedback_type": "motion"
            }

        # Check weak signal
        if ac_amplitude < self.MIN_AC_AMPLITUDE:
            return {
                "is_acceptable": False,
                "snr": snr,
                "peak_count": peak_count,
                "feedback_message": "손가락을 센서에 더 세게 눌러주세요",
                "feedback_type": "pressure_low"
            }

        # Check heart rate range (via peak count)
        if peak_count < self.MIN_PEAK_COUNT:
            return {
                "is_acceptable": False,
                "snr": snr,
                "peak_count": peak_count,
                "feedback_message": "신호가 약합니다 - 손가락 위치를 조정해주세요",
                "feedback_type": "weak"
            }

        if peak_count > self.MAX_PEAK_COUNT:
            return {
                "is_acceptable": False,
                "snr": snr,
                "peak_count": peak_count,
                "feedback_message": "손가락을 움직이지 말고 편안하게 측정해주세요",
                "feedback_type": "motion"
            }

        # Check overall SNR
        if snr < self.SNR_THRESHOLD:
            return {
                "is_acceptable": False,
                "snr": snr,
                "peak_count": peak_count,
                "feedback_message": "신호 품질 개선 필요 - 손가락을 가만히 유지해주세요",
                "feedback_type": "noise"
            }

        # All checks passed - good signal
        return {
            "is_acceptable": True,
            "snr": snr,
            "peak_count": peak_count,
            "feedback_message": "측정이 잘 되고 있습니다",
            "feedback_type": "good"
        }


# Singleton instance
_qc_service = PPGQualityControl()


def analyze_ppg_signal(ppg_data: list[float]) -> dict:
    """
    Convenience function to analyze PPG signal quality

    Args:
        ppg_data: List of PPG values (400 samples for 2-second window at 200Hz)

    Returns:
        Quality analysis results
    """
    return _qc_service.analyze_signal(ppg_data)
