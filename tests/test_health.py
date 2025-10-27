from server.health import ScraperHealthMonitor


def test_health_monitor_tracks_metrics():
    monitor = ScraperHealthMonitor(max_records=5)
    monitor.record_fetch(provider_id="p", duration_ms=100, success=True, cache_hit=True)
    monitor.record_fetch(provider_id="p", duration_ms=200, success=False, cache_hit=False, error_message="timeout")
    monitor.record_fetch(provider_id="p", duration_ms=150, success=True, cache_hit=False)

    summary = monitor.summary()
    assert summary["recent_fetches"] == 3
    assert 0 < summary["avg_duration_ms"] < 200
    assert summary["cache_hit_ratio"] > 0
    assert summary["requests_by_provider"]["p"] == 3
    assert "timeout" in summary["recent_errors"]
