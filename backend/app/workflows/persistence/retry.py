"""
CareBridge Workflow Retry & Resilience Policy (Phase 8)
Provides exponential backoff retry execution for transient network, LLM, or database failures.
Ensures long-running workflows recover gracefully without terminating unexpectedly.
"""

import time
import random
import logging
from typing import Callable, Any, Tuple, Type, Optional

logger = logging.getLogger("carebridge.workflows.retry")


class WorkflowRetryExhaustedError(Exception):
    """Raised when an operation has exhausted all configured retry attempts."""
    def __init__(self, message: str, attempts: int, last_error: Exception):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


class RetryConfig:
    """Configuration parameters for exponential backoff retries."""
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 0.2,
        backoff_multiplier: float = 2.0,
        max_delay: float = 5.0,
        jitter: bool = True,
        retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_multiplier = backoff_multiplier
        self.max_delay = max_delay
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or (
            ConnectionError,
            TimeoutError,
            IOError,
            RuntimeError
        )


class RetryPolicy:
    """Executes callables with exponential backoff and jitter."""

    @classmethod
    def execute_with_retry(
        cls,
        operation: Callable[..., Any],
        *args,
        config: Optional[RetryConfig] = None,
        operation_name: str = "workflow_operation",
        **kwargs
    ) -> Any:
        """
        Executes operation with retry logic.
        Catches specified transient errors and applies backoff.
        """
        cfg = config or RetryConfig()
        current_delay = cfg.initial_delay
        attempts = 0

        while True:
            attempts += 1
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                # Check if exception is retryable
                is_retryable = isinstance(e, cfg.retryable_exceptions)
                if not is_retryable or attempts > cfg.max_retries:
                    if attempts > cfg.max_retries:
                        logger.error(
                            f"[RetryPolicy] Operation '{operation_name}' failed after {attempts - 1} retries. Exhausted."
                        )
                        raise WorkflowRetryExhaustedError(
                            f"Operation '{operation_name}' failed after {attempts - 1} retries: {str(e)}",
                            attempts=attempts - 1,
                            last_error=e
                        ) from e
                    raise

                sleep_time = current_delay
                if cfg.jitter:
                    sleep_time = current_delay * (0.8 + 0.4 * random.random())

                logger.warning(
                    f"[RetryPolicy] Operation '{operation_name}' failed (Attempt {attempts}/{cfg.max_retries}): {e}. "
                    f"Retrying in {sleep_time:.2f}s..."
                )
                time.sleep(sleep_time)
                current_delay = min(current_delay * cfg.backoff_multiplier, cfg.max_delay)
