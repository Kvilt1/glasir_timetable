import logging
import math
import time
from typing import Optional

logger = logging.getLogger(__name__)

class ConcurrencyManager:
    """
    Manages dynamic concurrency limits based on success/failure feedback.

    Uses an Additive Increase, Multiplicative Decrease (AIMD) approach
    with modifications for minimum/maximum bounds and potential cooldowns.
    """

    def __init__(
        self,
        initial_limit: int,
        min_limit: int = 1,
        max_limit: int = 500,
        increase_step: int = 1,
        decrease_factor: float = 0.5,
        success_threshold: int = 10,  # Adjust limit after this many successes
        failure_cooldown_sec: float = 5.0, # Cooldown after a failure reduction
        name: Optional[str] = None,
        disabled: bool = False, # Add disabled flag
    ):
        """
        Initializes the ConcurrencyManager.

        Args:
            initial_limit: The starting concurrency limit.
            min_limit: The minimum allowed concurrency limit.
            max_limit: The maximum allowed concurrency limit.
            increase_step: How much to increase the limit upon sustained success (additive).
            decrease_factor: Factor to multiply the limit by upon failure (multiplicative).
            success_threshold: Number of consecutive successes required to trigger an increase.
            failure_cooldown_sec: Seconds to wait before allowing an increase after a failure reduction.
            name: An optional name for logging purposes.
            disabled: If True, dynamic adjustments are disabled.
        """
        if not (0 < min_limit <= initial_limit <= max_limit):
            raise ValueError("Concurrency limits invalid: min <= initial <= max must hold.")
        if not (0 < decrease_factor < 1):
            raise ValueError("Decrease factor must be between 0 and 1.")
        if increase_step <= 0:
            raise ValueError("Increase step must be positive.")
        if success_threshold <= 0:
            raise ValueError("Success threshold must be positive.")
        if failure_cooldown_sec < 0:
             raise ValueError("Failure cooldown cannot be negative.")

        self.min_limit = min_limit
        self.max_limit = max_limit
        self.increase_step = increase_step
        self.decrease_factor = decrease_factor
        self.success_threshold = success_threshold
        self.failure_cooldown_sec = failure_cooldown_sec
        self.name = name or "ConcurrencyManager"
        self.disabled = disabled # Store the disabled state

        self._current_limit = float(initial_limit) # Use float for multiplicative decrease
        self._success_streak = 0
        self._error_streak = 0 # Not strictly needed for AIMD but useful for potential future logic
        self._last_adjustment_time = time.monotonic()
        self._last_failure_time = 0.0 # Time of the last failure reduction

        log_message = (
            f"[{self.name}] Initialized: initial={initial_limit}, min={min_limit}, "
            f"max={max_limit}, inc_step={increase_step}, dec_factor={decrease_factor}, "
            f"succ_thresh={success_threshold}, fail_cooldown={failure_cooldown_sec}s"
        )
        if self.disabled:
            log_message += " (Dynamic adjustments DISABLED)"
        logger.info(log_message)

    def get_limit(self) -> int:
        """Returns the current concurrency limit as an integer."""
        return math.floor(self._current_limit)

    def get_current_limit(self) -> float:
        """Returns the current internal concurrency limit (can be float)."""
        return self._current_limit

    def report_success(self) -> None:
        """Reports a successful operation, potentially increasing the limit if not disabled."""
        self._success_streak += 1
        if self.disabled:
            return # Do nothing if disabled

        self._success_streak += 1
        self._error_streak = 0 # Reset error streak on success

        # Check if cooldown after failure is active
        current_time = time.monotonic()
        if current_time < self._last_failure_time + self.failure_cooldown_sec:
            # Still in cooldown, don't increase yet, but reset success streak
            # so we don't increase immediately after cooldown based on old successes
            self._success_streak = 0
            return

        if self._success_streak >= self.success_threshold:
            new_limit = min(self._current_limit + self.increase_step, self.max_limit)
            if new_limit > self._current_limit:
                old_limit_int = self.get_limit()
                self._current_limit = new_limit
                self._last_adjustment_time = current_time
                logger.info(
                    f"[{self.name}] Limit increased: {old_limit_int} -> {self.get_limit()} "
                    f"(success streak: {self._success_streak})"
                )
            # Reset streak after adjustment or hitting max limit
            self._success_streak = 0


    def report_failure(self) -> None:
        """Reports a failed operation, decreasing the limit immediately if not disabled."""
        self._error_streak += 1
        if self.disabled:
            logger.warning(f"[{self.name}] Failure reported but adjustments are disabled.")
            return # Do nothing if disabled

        self._error_streak += 1
        self._success_streak = 0 # Reset success streak on failure

        # Decrease limit multiplicatively, but not below min_limit
        new_limit = max(self._current_limit * self.decrease_factor, self.min_limit)

        if new_limit < self._current_limit:
            old_limit_int = self.get_limit()
            self._current_limit = new_limit
            current_time = time.monotonic()
            self._last_adjustment_time = current_time
            self._last_failure_time = current_time # Record time of failure reduction
            logger.warning(
                f"[{self.name}] Limit decreased: {old_limit_int} -> {self.get_limit()} "
                f"(failure detected)"
            )
        else:
             # Already at min_limit, log that a failure occurred but limit didn't change
             logger.warning(
                 f"[{self.name}] Failure detected but limit already at minimum ({self.get_limit()})"
             )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name='{self.name}', "
            f"current={self.get_limit()}, min={self.min_limit}, max={self.max_limit}, "
            f"success_streak={self._success_streak}/{self.success_threshold})"
        )