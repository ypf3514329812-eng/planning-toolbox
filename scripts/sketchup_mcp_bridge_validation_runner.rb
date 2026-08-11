# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'socket'

validation_dir = ENV.fetch('PT_SKETCHUP_VALIDATION_DIR')
plugin_main = ENV.fetch('PT_SKETCHUP_PLUGIN_MAIN')
report_path = File.join(validation_dir, 'sketchup_mcp_bridge_report.json')
config_path = File.join(ENV.fetch('APPDATA'), 'PlanningToolbox', 'mcp_bridge.json')
FileUtils.mkdir_p(validation_dir)

def bridge_health(config)
  payload = JSON.generate('command' => 'health', 'arguments' => {})
  socket = Socket.tcp(config.fetch('host'), config.fetch('port').to_i, connect_timeout: 1.0)
  socket.write(
    "POST /command HTTP/1.1\r\n" \
    "Host: #{config.fetch('host')}:#{config.fetch('port')}\r\n" \
    "Authorization: Bearer #{config.fetch('token')}\r\n" \
    "Content-Type: application/json\r\n" \
    "Content-Length: #{payload.bytesize}\r\n" \
    "Connection: close\r\n\r\n#{payload}"
  )
  response = socket.read
  status_line, body = response.split("\r\n\r\n", 2)
  raise "bridge returned an invalid response: #{status_line}" unless status_line.to_s.include?('200 OK')

  JSON.parse(body)
ensure
  socket.close if socket && !socket.closed?
end

UI.start_timer(3.0, false) do
  begin
    load(plugin_main) unless defined?(PlanningToolbox::SketchUpMcpBridge)
    config = JSON.parse(File.open(config_path, 'r:bom|utf-8', &:read))
    response = bridge_health(config)
    health = response.fetch('data')
    raise "bridge command failed: #{response.inspect}" unless response['ok']
    raise "bridge version mismatch: #{config['version']}" unless config['version'] == '0.58.1'
    raise "wrong bridge owner: #{config['process_id']}" unless config['process_id'].to_i == Process.pid
    raise "bridge is not ready: #{health.inspect}" unless health['status'] == 'ready'
    raise 'bridge accept thread is not alive' unless health['thread_alive']

    File.write(
      report_path,
      JSON.pretty_generate(
        'status' => 'PASS',
        'process_id' => Process.pid,
        'config' => config.reject { |key, _value| key == 'token' },
        'health' => health
      )
    )
  rescue StandardError => error
    File.write(
      report_path,
      JSON.pretty_generate(
        'status' => 'FAIL',
        'process_id' => Process.pid,
        'error_class' => error.class.name,
        'error_message' => error.message,
        'backtrace' => error.backtrace&.first(20)
      )
    )
  ensure
    UI.start_timer(1.0, false) { Sketchup.quit }
  end
end
