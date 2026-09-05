"""Tests for Catch's single-instance guard."""

from core.instance import SingleInstance


def test_instance_can_be_acquired_and_released() -> None:
    instance = SingleInstance("Catch.Test.Instance")

    assert instance.acquire() is True
    assert instance.acquire() is True
    instance.release()
    assert instance._handle is None


def test_second_acquisition_is_rejected_on_windows() -> None:
    first = SingleInstance("Catch.Test.Exclusive.Instance")
    second = SingleInstance("Catch.Test.Exclusive.Instance")

    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
        second.release()