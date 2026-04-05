# Looker Studio Dashboard Setup

This project now includes a Looker Studio-ready analytics layer in the backend and a Google Apps Script community connector scaffold in `looker_studio_connector/`.

## Backend datasets

The following endpoints are designed for BI/reporting and are better suited to Looker Studio than the raw operational APIs:

- `GET /analytics/kpis`
- `GET /analytics/trends`
- `GET /analytics/breakdown`
- `GET /analytics/factors`
- `GET /analytics/alerts/trends`
- `GET /analytics/alerts/breakdown`
- `GET /analytics/events`

All endpoints accept the same bearer token as the main application and support:

- `locomotive_id`
- `from`
- `to`

Trend endpoints also support:

- `bucket=15min|hour|day`

Breakdown endpoints also support:

- `dimension=...`

## Recommended dashboard pages

### 1. Executive Overview

Use dataset: `KPI Summary`

Add scorecards for:

- `avg_health_score`
- `critical_event_rate_pct`
- `alerts_total`
- `critical_alerts_total`
- `avg_availability_pct`
- `avg_mtbf_h`
- `avg_mttr_h`
- `avg_speed_limit_utilization_pct`

Add a compact table with:

- `scope_locomotive_id`
- `events`
- `locomotives`
- `avg_fuel_level_pct`
- `avg_electric_power_kw`
- `avg_reservoir_pressure_mpa`

### 2. Operational Trends

Use dataset: `Operational Trends`

Recommended charts:

- Time series: `bucket_start` vs `avg_health_score`
- Time series: `bucket_start` vs `critical_event_count`
- Combo chart: `bucket_start` vs `avg_speed_kmh` and `avg_speed_limit_utilization_pct`
- Multi-line chart: `bucket_start` vs `avg_engine_oil_temperature_c`, `avg_coolant_temperature_c`
- Multi-line chart: `bucket_start` vs `avg_wheel_slip_ratio_pct`, `avg_vibration_mms`, `avg_reservoir_pressure_mpa`

### 3. Alert Intelligence

Use datasets: `Alert Trends` and `Alert Breakdown`

Recommended charts:

- Time series: `bucket_start` vs `alerts_total`
- Stacked bar: `dimension_value` by `alerts_total` with `dimension_name=severity`
- Bar chart: `dimension_value` by `alerts_total` with `dimension_name=source`
- Bar chart: `dimension_value` by `critical_share_pct` with `dimension_name=code`
- Table: `dimension_value`, `alerts_total`, `locomotives_affected`

### 4. Health Breakdown

Use dataset: `Breakdown`

Recommended charts:

- Donut chart: `dimension_value` by `events` with `dimension_name=health_grade`
- Bar chart: `dimension_value` by `avg_health_score` with `dimension_name=locomotive_type`
- Bar chart: `dimension_value` by `critical_event_rate_pct` with `dimension_name=rail_surface_state`
- Bar chart: `dimension_value` by `avg_alerts_per_event` with `dimension_name=top_factor_category`

### 5. Factor Analysis

Use dataset: `Factor Breakdown`

Recommended charts:

- Horizontal bar: `factor_label` by `occurrences`
- Horizontal bar: `factor_label` by `avg_penalty_points`
- Heatmap/table: `factor_category`, `factor_label`, `affected_locomotives`, `max_penalty_points`

### 6. Event Explorer

Use dataset: `Flat Event Rows`

Recommended charts:

- Detailed table with filters for `locomotive_id`, `locomotive_type`, `health_grade`, `rail_surface_state`
- Scatter chart: `wheel_slip_ratio_pct` vs `health_score`
- Scatter chart: `engine_oil_temperature_c` vs `health_score`
- Scatter chart: `vibration_amplitude_mms` vs `alert_count`
- Geo chart if you later add normalized region/station dimensions

## Suggested report controls

Add report-level controls for:

- Date range
- `locomotive_id`
- `locomotive_type`
- `health_grade`
- `rail_surface_state`

## Community connector setup

1. Go to [Apps Script](https://script.google.com/).
2. Create a new project.
3. Replace the default `Code.gs` with `looker_studio_connector/Code.js`.
4. Replace `appsscript.json` with `looker_studio_connector/appsscript.json`.
5. In `Code.js`, set your deployed backend URL when prompted in the connector config.
6. Deploy the Apps Script project as a Looker Studio community connector.
7. In Looker Studio, choose the deployed connector and authenticate with:
   - Path: your backend base URL, for example `https://your-api.example.com` or `http://127.0.0.1:8000`
   - Username: backend username
   - Password: backend password
8. Then choose:
   - dataset type
   - optional locomotive filter
9. Build report pages using the recommended chart layouts above.

## Important note

The connector authenticates by calling the backend `POST /auth/login` endpoint with the same credentials used in the main app, then uses the returned bearer token for analytics requests.

## If the connector does not open

Common fixes:

- Delete the default Apps Script file that still references `myFunction`.
- Make sure the project manifest includes the external request scope.
- Use `Deploy -> Test deployments` and open the copied connector URL from there.
- If Looker cached bad credentials, use `resetAuth` in Apps Script and reconnect.
