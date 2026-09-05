from tools.weather import get_weather


def test_weather_uses_saved_profile_city(monkeypatch) -> None:
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "weather": [{"description": "clear sky"}],
                "main": {"temp": 25, "feels_like": 26, "humidity": 40},
                "wind": {"speed": 2},
            }

    monkeypatch.setattr("tools.weather.get_secret", lambda name: "test-key")
    monkeypatch.setattr("tools.weather.weather_location", lambda: {"city": "Marrakesh", "country": "Morocco"})
    monkeypatch.setattr("tools.weather.httpx.get", lambda url, params, timeout: captured.update(params=params) or Response())

    result = get_weather()

    assert result["success"] is True
    assert captured["params"]["q"] == "Marrakesh,Morocco"
    assert "25°C" in result["message"]


def test_weather_accepts_explicit_city(monkeypatch) -> None:
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"weather": [{"description": "rain"}], "main": {}, "wind": {}}

    monkeypatch.setattr("tools.weather.get_secret", lambda name: "test-key")
    monkeypatch.setattr("tools.weather.httpx.get", lambda url, params, timeout: captured.update(params=params) or Response())

    assert get_weather("London,uk")["success"] is True
    assert captured["params"]["q"] == "London,uk"
