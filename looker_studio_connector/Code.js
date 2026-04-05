var cc = DataStudioApp.createCommunityConnector();

function getAuthType() {
  return cc
    .newAuthTypeResponse()
    .setAuthType(cc.AuthType.PATH_USER_PASS)
    .setHelpUrl('https://github.com/mundmina/hackNU_26/blob/main/docs/looker-studio-dashboard.md')
    .build();
}

function setCredentials(request) {
  var creds = request.pathUserPass;
  var userProperties = PropertiesService.getUserProperties();
  userProperties.setProperty('ls.base_url', sanitizeBaseUrl_(creds.path));
  userProperties.setProperty('ls.username', creds.username || '');
  userProperties.setProperty('ls.password', creds.password || '');
  return {
    errorCode: 'NONE'
  };
}

function isAuthValid() {
  var userProperties = PropertiesService.getUserProperties();
  return Boolean(
    userProperties.getProperty('ls.base_url') &&
    userProperties.getProperty('ls.username') &&
    userProperties.getProperty('ls.password')
  );
}

function resetAuth() {
  var userProperties = PropertiesService.getUserProperties();
  userProperties.deleteProperty('ls.base_url');
  userProperties.deleteProperty('ls.username');
  userProperties.deleteProperty('ls.password');
  userProperties.deleteProperty('ls.token');
}

function getConfig() {
  var config = cc.getConfig();
  config.setDateRangeRequired(true);

  config
    .newInfo()
    .setId('instructions')
    .setText('Authenticate using PATH / username / password. Put your backend base URL into the PATH field, then choose a dataset here.');

  config
    .newTextInput()
    .setId('locomotive_id')
    .setName('Optional Locomotive ID Filter')
    .setHelpText('Leave blank to query the entire fleet.');

  config
    .newSelectSingle()
    .setId('dataset')
    .setName('Dataset')
    .addOption(config.newOptionBuilder().setLabel('KPI Summary').setValue('kpis'))
    .addOption(config.newOptionBuilder().setLabel('Operational Trends').setValue('trends'))
    .addOption(config.newOptionBuilder().setLabel('Breakdown').setValue('breakdown'))
    .addOption(config.newOptionBuilder().setLabel('Factor Breakdown').setValue('factors'))
    .addOption(config.newOptionBuilder().setLabel('Alert Trends').setValue('alerts_trends'))
    .addOption(config.newOptionBuilder().setLabel('Alert Breakdown').setValue('alerts_breakdown'))
    .addOption(config.newOptionBuilder().setLabel('Flat Event Rows').setValue('events'));

  config
    .newSelectSingle()
    .setId('bucket')
    .setName('Trend Bucket')
    .addOption(config.newOptionBuilder().setLabel('15 Minutes').setValue('15min'))
    .addOption(config.newOptionBuilder().setLabel('Hour').setValue('hour'))
    .addOption(config.newOptionBuilder().setLabel('Day').setValue('day'));

  config
    .newSelectSingle()
    .setId('breakdown_dimension')
    .setName('Breakdown Dimension')
    .addOption(config.newOptionBuilder().setLabel('Health Grade').setValue('health_grade'))
    .addOption(config.newOptionBuilder().setLabel('Health Band').setValue('health_band'))
    .addOption(config.newOptionBuilder().setLabel('Locomotive Type').setValue('locomotive_type'))
    .addOption(config.newOptionBuilder().setLabel('Rail Surface State').setValue('rail_surface_state'))
    .addOption(config.newOptionBuilder().setLabel('Top Factor Category').setValue('top_factor_category'))
    .addOption(config.newOptionBuilder().setLabel('Top Factor Label').setValue('top_factor_label'))
    .addOption(config.newOptionBuilder().setLabel('Alert Source').setValue('source'))
    .addOption(config.newOptionBuilder().setLabel('Alert Severity').setValue('severity'))
    .addOption(config.newOptionBuilder().setLabel('Alert Code').setValue('code'))
    .addOption(config.newOptionBuilder().setLabel('Alert Status').setValue('status'));

  return config.build();
}

function getSchema(request) {
  request = request || {};
  request.configParams = request.configParams || {};
  return {
    schema: getFieldsForDataset_(request.configParams.dataset || 'kpis').build()
  };
}

function getData(request) {
  request = request || {};
  request.configParams = request.configParams || {};
  var dataset = request.configParams.dataset || 'kpis';
  var requestedFieldIds = request.fields.map(function(field) {
    return field.name;
  });
  var fields = getFieldsForDataset_(dataset);
  var requestedFields = fields.forIds(requestedFieldIds);
  var data = fetchDataset_(request);

  var rows = data.map(function(item) {
    return {
      values: requestedFieldIds.map(function(fieldId) {
        var value = item[fieldId];
        if (value === null || value === undefined) {
          return '';
        }
        if (fieldId === 'event_date' && typeof value === 'string') {
          return value.replace(/-/g, '');
        }
        if ((fieldId === 'timestamp' || fieldId === 'bucket_start' || fieldId === 'generated_at') && typeof value === 'string') {
          return value.replace(/[-:]/g, '').split('.')[0].replace('T', '');
        }
        return value;
      })
    };
  });

  return {
    schema: requestedFields.build(),
    rows: rows
  };
}

function getFieldsForDataset_(dataset) {
  var fields = cc.getFields();
  var types = cc.FieldType;
  var aggs = cc.AggregationType;

  function dimension(id, name, type) {
    return fields.newDimension().setId(id).setName(name).setType(type);
  }

  function metric(id, name) {
    return fields.newMetric().setId(id).setName(name).setType(types.NUMBER).setAggregation(aggs.AUTO);
  }

  if (dataset === 'kpis') {
    dimension('generated_at', 'Generated At', types.YEAR_MONTH_DAY_SECOND);
    dimension('scope_locomotive_id', 'Scope Locomotive', types.TEXT);
    metric('events', 'Events');
    metric('locomotives', 'Locomotives');
    metric('avg_health_score', 'Avg Health Score');
    metric('min_health_score', 'Min Health Score');
    metric('critical_event_rate_pct', 'Critical Event Rate %');
    metric('avg_speed_kmh', 'Avg Speed km/h');
    metric('avg_speed_limit_utilization_pct', 'Avg Speed Limit Utilization %');
    metric('avg_alerts_per_event', 'Avg Alerts per Event');
    metric('alert_events_pct', 'Alert Events %');
    metric('alerts_total', 'Alerts Total');
    metric('critical_alerts_total', 'Critical Alerts Total');
    metric('avg_availability_pct', 'Avg Availability %');
    metric('avg_mtbf_h', 'Avg MTBF (h)');
    metric('avg_mttr_h', 'Avg MTTR (h)');
    metric('avg_fuel_level_pct', 'Avg Fuel Level %');
    metric('avg_electric_power_kw', 'Avg Electric Power kW');
    metric('avg_wheel_slip_ratio_pct', 'Avg Wheel Slip %');
    metric('avg_vibration_mms', 'Avg Vibration mm/s');
    metric('avg_brake_pad_remaining_pct', 'Avg Brake Pad Remaining %');
    metric('avg_reservoir_pressure_mpa', 'Avg Reservoir Pressure MPa');
    return fields;
  }

  if (dataset === 'trends') {
    dimension('bucket_start', 'Bucket Start', types.YEAR_MONTH_DAY_SECOND);
    dimension('scope_locomotive_id', 'Scope Locomotive', types.TEXT);
    metric('events', 'Events');
    metric('avg_health_score', 'Avg Health Score');
    metric('min_health_score', 'Min Health Score');
    metric('critical_event_count', 'Critical Event Count');
    metric('avg_speed_kmh', 'Avg Speed km/h');
    metric('max_speed_kmh', 'Max Speed km/h');
    metric('avg_speed_limit_utilization_pct', 'Avg Speed Limit Utilization %');
    metric('avg_alerts_per_event', 'Avg Alerts per Event');
    metric('avg_engine_oil_temperature_c', 'Avg Oil Temp C');
    metric('avg_coolant_temperature_c', 'Avg Coolant Temp C');
    metric('avg_wheel_slip_ratio_pct', 'Avg Wheel Slip %');
    metric('avg_vibration_mms', 'Avg Vibration mm/s');
    metric('avg_reservoir_pressure_mpa', 'Avg Reservoir Pressure MPa');
    metric('avg_availability_pct', 'Avg Availability %');
    return fields;
  }

  if (dataset === 'breakdown') {
    dimension('dimension_name', 'Dimension Name', types.TEXT);
    dimension('dimension_value', 'Dimension Value', types.TEXT);
    dimension('scope_locomotive_id', 'Scope Locomotive', types.TEXT);
    metric('events', 'Events');
    metric('locomotives', 'Locomotives');
    metric('avg_health_score', 'Avg Health Score');
    metric('critical_event_rate_pct', 'Critical Event Rate %');
    metric('avg_alerts_per_event', 'Avg Alerts per Event');
    metric('avg_speed_kmh', 'Avg Speed km/h');
    metric('avg_wheel_slip_ratio_pct', 'Avg Wheel Slip %');
    metric('avg_vibration_mms', 'Avg Vibration mm/s');
    return fields;
  }

  if (dataset === 'factors') {
    dimension('factor_label', 'Factor Label', types.TEXT);
    dimension('factor_category', 'Factor Category', types.TEXT);
    dimension('scope_locomotive_id', 'Scope Locomotive', types.TEXT);
    metric('occurrences', 'Occurrences');
    metric('affected_locomotives', 'Affected Locomotives');
    metric('avg_penalty_points', 'Avg Penalty Points');
    metric('max_penalty_points', 'Max Penalty Points');
    return fields;
  }

  if (dataset === 'alerts_trends') {
    dimension('bucket_start', 'Bucket Start', types.YEAR_MONTH_DAY_SECOND);
    dimension('scope_locomotive_id', 'Scope Locomotive', types.TEXT);
    metric('alerts_total', 'Alerts Total');
    metric('critical_alerts_total', 'Critical Alerts Total');
    metric('warning_alerts_total', 'Warning Alerts Total');
    metric('locomotives_affected', 'Locomotives Affected');
    return fields;
  }

  if (dataset === 'alerts_breakdown') {
    dimension('dimension_name', 'Dimension Name', types.TEXT);
    dimension('dimension_value', 'Dimension Value', types.TEXT);
    dimension('scope_locomotive_id', 'Scope Locomotive', types.TEXT);
    metric('alerts_total', 'Alerts Total');
    metric('critical_share_pct', 'Critical Share %');
    metric('locomotives_affected', 'Locomotives Affected');
    return fields;
  }

  dimension('event_id', 'Event ID', types.TEXT);
  dimension('timestamp', 'Timestamp', types.YEAR_MONTH_DAY_SECOND);
  dimension('event_date', 'Event Date', types.YEAR_MONTH_DAY);
  dimension('locomotive_id', 'Locomotive ID', types.TEXT);
  dimension('locomotive_type', 'Locomotive Type', types.TEXT);
  dimension('health_grade', 'Health Grade', types.TEXT);
  dimension('health_band', 'Health Band', types.TEXT);
  dimension('rail_surface_state', 'Rail Surface State', types.TEXT);
  dimension('top_factor_label', 'Top Factor Label', types.TEXT);
  dimension('top_factor_category', 'Top Factor Category', types.TEXT);
  metric('health_score', 'Health Score');
  metric('speed_kmh', 'Speed km/h');
  metric('speed_limit_kmh', 'Speed Limit km/h');
  metric('speed_limit_utilization_pct', 'Speed Limit Utilization %');
  metric('tractive_effort_kn', 'Tractive Effort kN');
  metric('wheel_slip_ratio_pct', 'Wheel Slip %');
  metric('adhesion_coefficient', 'Adhesion Coefficient');
  metric('battery_voltage_v', 'Battery Voltage V');
  metric('electric_power_kw', 'Electric Power kW');
  metric('fuel_level_pct', 'Fuel Level %');
  metric('fuel_consumption_lph', 'Fuel Consumption L/h');
  metric('engine_oil_temperature_c', 'Oil Temp C');
  metric('coolant_temperature_c', 'Coolant Temp C');
  metric('engine_oil_pressure_mpa', 'Oil Pressure MPa');
  metric('exhaust_gas_temperature_c', 'Exhaust Gas Temp C');
  metric('traction_motor_winding_temp_c', 'Motor Winding Temp C');
  metric('vibration_amplitude_mms', 'Vibration mm/s');
  metric('main_reservoir_pressure_mpa', 'Reservoir Pressure MPa');
  metric('brake_pad_wear_pct_remaining', 'Brake Pad Remaining %');
  metric('active_error_codes', 'Active Error Codes');
  metric('alert_count', 'Alert Count');
  metric('critical_alert_count', 'Critical Alert Count');
  metric('locomotive_availability_pct', 'Availability %');
  metric('mtbf_h', 'MTBF h');
  metric('mttr_h', 'MTTR h');
  metric('distance_since_last_overhaul_km', 'Distance Since Overhaul km');
  metric('track_gradient_permille', 'Track Gradient ‰');
  metric('top_factor_penalty_points', 'Top Factor Penalty Points');
  return fields;
}

function fetchDataset_(request) {
  var params = request.configParams || {};
  var dataset = params.dataset || 'kpis';
  var baseUrl = sanitizeBaseUrl_(params.base_url || getConfigParamFallbackBaseUrl_());
  var url = baseUrl + '/analytics';
  var query = [];

  if (request.dateRange && request.dateRange.startDate && request.dateRange.endDate) {
    query.push('from=' + encodeURIComponent(request.dateRange.startDate + 'T00:00:00Z'));
    query.push('to=' + encodeURIComponent(request.dateRange.endDate + 'T23:59:59Z'));
  }

  if (params.locomotive_id) {
    query.push('locomotive_id=' + encodeURIComponent(params.locomotive_id));
  }

  if (dataset === 'trends') {
    url += '/trends';
    query.push('bucket=' + encodeURIComponent(params.bucket || 'hour'));
  } else if (dataset === 'breakdown') {
    url += '/breakdown';
    query.push('dimension=' + encodeURIComponent(params.breakdown_dimension || 'health_grade'));
  } else if (dataset === 'factors') {
    url += '/factors';
  } else if (dataset === 'alerts_trends') {
    url += '/alerts/trends';
    query.push('bucket=' + encodeURIComponent(params.bucket || 'hour'));
  } else if (dataset === 'alerts_breakdown') {
    url += '/alerts/breakdown';
    query.push('dimension=' + encodeURIComponent(params.breakdown_dimension || 'source'));
  } else if (dataset === 'events') {
    url += '/events';
  } else {
    url += '/kpis';
  }

  if (query.length) {
    url += '?' + query.join('&');
  }

  var response = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: {
      Authorization: 'Bearer ' + getAccessToken_(),
      'ngrok-skip-browser-warning': '1'
    },
    muteHttpExceptions: true
  });

  if (response.getResponseCode() >= 300) {
    throwConnectorError_('Backend analytics request failed: ' + response.getContentText());
  }

  return JSON.parse(response.getContentText());
}

function getAccessToken_() {
  var userProperties = PropertiesService.getUserProperties();
  var username = userProperties.getProperty('ls.username');
  var password = userProperties.getProperty('ls.password');
  var baseUrl = sanitizeBaseUrl_(getConfigParamFallbackBaseUrl_());
  if (!username || !password || !baseUrl) {
    throw new Error('Missing connector credentials or base URL.');
  }

  var response = UrlFetchApp.fetch(baseUrl + '/auth/login', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'ngrok-skip-browser-warning': '1'
    },
    payload: JSON.stringify({
      username: username,
      password: password
    }),
    muteHttpExceptions: true
  });

  if (response.getResponseCode() >= 300) {
    throw new Error('Authentication failed: ' + response.getContentText());
  }

  return JSON.parse(response.getContentText()).access_token;
}

function sanitizeBaseUrl_(url) {
  return (url || '').replace(/\/+$/, '');
}

function getConfigParamFallbackBaseUrl_() {
  var userProperties = PropertiesService.getUserProperties();
  return userProperties.getProperty('ls.base_url') || '';
}

function isAdminUser() {
  return true;
}

function throwConnectorError_(message) {
  cc.newUserError()
    .setDebugText(message)
    .setText(message)
    .throwException();
}
