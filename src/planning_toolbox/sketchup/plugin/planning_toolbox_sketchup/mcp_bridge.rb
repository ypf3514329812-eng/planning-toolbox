# frozen_string_literal: true

# Local, allow-listed bridge for Planning Toolbox MCP clients.
#
# The bridge deliberately exposes a small command surface instead of Ruby
# evaluation.  HTTP is bound to loopback only and every request needs the
# token written to the local bridge configuration file.

require 'socket'
require 'json'
require 'fileutils'
require 'securerandom'
require 'time'

module PlanningToolbox
  module SketchUpMcpBridge
    HOST = '127.0.0.1'
    DEFAULT_PORT = 8765
    VERSION = '0.59.0'
    WATCHDOG_INTERVAL = 3.0
    CONFIG_DIR = File.join(ENV.fetch('APPDATA', Dir.tmpdir), 'PlanningToolbox')
    CONFIG_PATH = ENV.fetch(
      'PLANNING_TOOLBOX_MCP_CONFIG',
      File.join(CONFIG_DIR, 'mcp_bridge.json')
    )
    LOG_PATH = File.join(CONFIG_DIR, 'mcp_bridge.log')
    ROOT_PATH = ENV.fetch('PLANNING_TOOLBOX_ROOT', 'C:/AutoOS/OS1')
    ATTRIBUTE_DICTIONARY = 'Planning Toolbox'
    MAX_REQUEST_BYTES = 2 * 1024 * 1024

    COMPONENT_ASSETS = {
      'tree_large' => {
        'skp_file' => 'pt_tree_large.skp', 'source_id' => 'kenney-city-kit-suburban-2.0',
        'license' => 'CC0-1.0', 'target_bounds_m' => [4.8, 4.8, 7.0]
      },
      'tree_small' => {
        'skp_file' => 'pt_tree_small.skp', 'source_id' => 'kenney-city-kit-suburban-2.0',
        'license' => 'CC0-1.0', 'target_bounds_m' => [3.2, 3.2, 4.2]
      },
      'planter' => {
        'skp_file' => 'pt_planter.skp', 'source_id' => 'kenney-city-kit-suburban-2.0',
        'license' => 'CC0-1.0', 'target_bounds_m' => [1.2, 0.9, 0.55]
      },
      'street_light' => {
        'skp_file' => 'pt_street_light.skp', 'source_id' => 'kenney-city-kit-roads-2.0',
        'license' => 'CC0-1.0', 'target_bounds_m' => [0.45, 1.8, 6.0]
      },
      'awning_wide' => {
        'skp_file' => 'pt_awning_wide.skp', 'source_id' => 'kenney-city-kit-commercial-2.1',
        'license' => 'CC0-1.0', 'target_bounds_m' => [3.8, 1.2, 0.65]
      },
      'overhang_wide' => {
        'skp_file' => 'pt_overhang_wide.skp', 'source_id' => 'kenney-city-kit-commercial-2.1',
        'license' => 'CC0-1.0', 'target_bounds_m' => [3.4, 1.0, 0.45]
      },
      'parasol' => {
        'skp_file' => 'pt_parasol.skp', 'source_id' => 'kenney-city-kit-commercial-2.1',
        'license' => 'CC0-1.0', 'target_bounds_m' => [3.0, 3.0, 2.7]
      },
      'road_crossing' => {
        'skp_file' => 'pt_road_crossing.skp', 'source_id' => 'kaykit-city-builder-bits-1.0',
        'license' => 'CC0-1.0', 'target_bounds_m' => [8.0, 8.0, 0.12]
      },
      'traffic_light' => {
        'skp_file' => 'pt_traffic_light.skp', 'source_id' => 'kaykit-city-builder-bits-1.0',
        'license' => 'CC0-1.0', 'target_bounds_m' => [0.9, 0.8, 5.0]
      },
      'parked_car' => {
        'native_generator' => 'parked_car', 'skp_file' => 'pt_parked_car.skp',
        'source_id' => 'planning-toolbox-native-components-2026', 'license' => 'CC0-1.0',
        'target_bounds_m' => [4.8, 2.0, 1.5]
      },
      'bench' => {
        'native_generator' => 'bench', 'skp_file' => 'pt_bench.skp',
        'source_id' => 'planning-toolbox-native-components-2026', 'license' => 'CC0-1.0',
        'target_bounds_m' => [1.8, 0.65, 1.2]
      },
      'shrub_cluster' => {
        'native_generator' => 'shrub_cluster', 'skp_file' => 'pt_shrub_cluster.skp',
        'source_id' => 'planning-toolbox-native-components-2026', 'license' => 'CC0-1.0',
        'target_bounds_m' => [2.4, 1.6, 1.4]
      },
      'bollard' => {
        'native_generator' => 'bollard', 'skp_file' => 'pt_bollard.skp',
        'source_id' => 'planning-toolbox-native-components-2026', 'license' => 'CC0-1.0',
        'target_bounds_m' => [0.32, 0.32, 1.0]
      },
      'bus_shelter' => {
        'native_generator' => 'bus_shelter', 'skp_file' => 'pt_bus_shelter.skp',
        'source_id' => 'planning-toolbox-native-components-2026', 'license' => 'CC0-1.0',
        'target_bounds_m' => [4.0, 1.6, 3.2]
      }
    }.freeze

    @running = false
    @passive = false
    @stopping = false
    @dispatch_scheduled = false
    @dispatch_mutex = Mutex.new
    @pending = Queue.new
    @watchdog_timer = nil
    @last_error = nil
    @instance_id = nil

    module_function

    def start!
      return true if @running && @thread && @thread.alive?

      @stopping = false
      @passive = false
      close_server
      requested_port = ENV.fetch('PLANNING_TOOLBOX_MCP_PORT', DEFAULT_PORT.to_s).to_i
      requested_port = 0 unless requested_port.between?(1024, 65_535)
      @token = SecureRandom.hex(24)
      @instance_id = SecureRandom.hex(12)
      begin
        @server = TCPServer.new(HOST, requested_port)
      rescue Errno::EADDRINUSE, Errno::EACCES => error
        existing = read_config
        if bridge_alive?(existing)
          @passive = true
          @last_error = nil
          schedule_watchdog
          Sketchup.status_text = 'Planning Toolbox MCP 已由另一个 SketchUp 实例提供。'
          return false
        end
        log_error("preferred port #{requested_port} unavailable; using a dynamic port", error)
        @server = TCPServer.new(HOST, 0)
      end
      @port = @server.addr[1]
      @running = true
      write_config
      @thread = Thread.new { accept_loop }
      @thread.abort_on_exception = false if @thread.respond_to?(:abort_on_exception=)
      @thread.report_on_exception = false if @thread.respond_to?(:report_on_exception=)
      @last_error = nil
      schedule_watchdog
      Sketchup.status_text = "Planning Toolbox MCP 已启动：#{HOST}:#{@port}"
      true
    rescue StandardError => error
      @running = false
      @passive = false
      @last_error = error.message
      close_server
      log_error('bridge start failed', error)
      schedule_watchdog unless @stopping
      Sketchup.status_text = "Planning Toolbox MCP 未启动：#{error.message}"
      false
    end

    def stop!
      @stopping = true
      @running = false
      @passive = false
      close_server
      if @thread && @thread != Thread.current
        @thread.join(0.25)
      end
      @thread = nil
      delete_config_if_owned
      stop_watchdog
    rescue StandardError
      nil
    end

    def close_server
      @server.close if @server && !@server.closed?
    rescue StandardError
      nil
    ensure
      @server = nil
    end

    def read_config
      return nil unless File.file?(CONFIG_PATH)

      JSON.parse(File.open(CONFIG_PATH, 'r:bom|utf-8', &:read))
    rescue StandardError
      nil
    end

    def delete_config_if_owned
      config = read_config
      return unless config
      return unless config['instance_id'].to_s == @instance_id.to_s
      return unless config['token'].to_s == @token.to_s

      File.delete(CONFIG_PATH) if File.file?(CONFIG_PATH)
    rescue StandardError
      nil
    end

    def bridge_alive?(config)
      return false unless config.is_a?(Hash)

      port = config['port'].to_i
      token = config['token'].to_s
      return false unless port.between?(1024, 65_535) && !token.empty?

      payload = JSON.generate('command' => 'health', 'arguments' => {})
      socket = Socket.tcp(HOST, port, connect_timeout: 0.5)
      socket.write(
        "POST /command HTTP/1.1\r\n" \
        "Host: #{HOST}:#{port}\r\n" \
        "Authorization: Bearer #{token}\r\n" \
        "Content-Type: application/json\r\n" \
        "Content-Length: #{payload.bytesize}\r\n" \
        "Connection: close\r\n\r\n#{payload}"
      )
      ready = IO.select([socket], nil, nil, 0.8)
      return false unless ready

      response = socket.read
      response.include?('200 OK') && response.include?('"status":"ready"')
    rescue StandardError
      false
    ensure
      socket.close if socket && !socket.closed?
    end

    def schedule_watchdog
      return if @watchdog_timer

      @watchdog_timer = UI.start_timer(WATCHDOG_INTERVAL, true) { watchdog_tick }
    rescue StandardError => error
      log_error('watchdog could not start', error)
    end

    def stop_watchdog
      return unless @watchdog_timer

      UI.stop_timer(@watchdog_timer)
    rescue StandardError
      nil
    ensure
      @watchdog_timer = nil
    end

    def watchdog_tick
      return if @stopping

      if @running
        healthy = @server && !@server.closed? && @thread && @thread.alive?
        return if healthy

        log_error('owner bridge thread stopped unexpectedly')
        @running = false
        close_server
        delete_config_if_owned
        start!
      elsif @passive
        return if bridge_alive?(read_config)

        @passive = false
        start!
      else
        start!
      end
    rescue StandardError => error
      @last_error = error.message
      log_error('watchdog recovery failed', error)
    end

    def log_error(message, error = nil)
      FileUtils.mkdir_p(CONFIG_DIR)
      File.delete(LOG_PATH) if File.file?(LOG_PATH) && File.size(LOG_PATH) > 262_144
      detail = error ? "#{error.class}: #{error.message}" : ''
      File.open(LOG_PATH, 'a:utf-8') do |file|
        file.puts("#{Time.now.utc.iso8601} #{message} #{detail}".strip)
      end
    rescue StandardError
      nil
    end

    def write_config
      FileUtils.mkdir_p(File.dirname(CONFIG_PATH))
      File.write(
        CONFIG_PATH,
        JSON.pretty_generate(
          'host' => HOST,
          'port' => @port,
          'token' => @token,
          'version' => VERSION,
          'process_id' => Process.pid,
          'instance_id' => @instance_id,
          'started_at' => Time.now.utc.iso8601,
          'allowed_root' => File.expand_path(ROOT_PATH),
          'commands' => allowed_commands
        )
      )
    end

    def allowed_commands
      %w[
        health inspect_model list_tags set_tag_visibility import_handoff
        place_component save_model_as export_preview quality_check
      ]
    end

    def accept_loop
      unexpected_error = nil
      while @running
        begin
          socket = @server.accept
          Thread.new(socket) { |client| handle_client(client) }
        rescue IOError, Errno::EBADF
          break
        rescue StandardError => error
          unexpected_error = error
          break
        end
      end
    ensure
      if !@stopping && @running
        @running = false
        @last_error = unexpected_error ? unexpected_error.message : 'accept loop stopped'
        log_error('accept loop stopped', unexpected_error)
        close_server
        delete_config_if_owned
      end
    end

    def handle_client(client)
      request_line = client.gets
      return client.close unless request_line

      method, path, = request_line.split(' ', 3)
      headers = {}
      while (line = client.gets)
        line = line.strip
        break if line.empty?
        key, value = line.split(':', 2)
        headers[key.to_s.downcase] = value.to_s.strip
      end
      length = headers.fetch('content-length', '0').to_i
      raise ArgumentError, 'request body is too large' if length > MAX_REQUEST_BYTES
      body = length.positive? ? client.read(length) : ''

      unless method == 'POST' && path == '/command'
        respond(client, 404, { 'ok' => false, 'error' => 'not found' })
        return
      end
      unless headers['authorization'].to_s == "Bearer #{@token}"
        respond(client, 401, { 'ok' => false, 'error' => 'unauthorized' })
        return
      end

      request = JSON.parse(body)
      if request['command'].to_s == 'health'
        respond(
          client,
          200,
          {
            'ok' => true,
            'data' => {
              'status' => 'ready',
              'port' => @port,
              'version' => VERSION,
              'process_id' => Process.pid,
              'instance_id' => @instance_id,
              'thread_alive' => !!(@thread && @thread.alive?)
            }
          }
        )
        return
      end
      response_queue = Queue.new
      @pending << [request, response_queue]
      schedule_dispatch
      response = response_queue.pop
      respond(client, 200, response)
    rescue JSON::ParserError
      respond(client, 400, { 'ok' => false, 'error' => 'invalid JSON' })
    rescue StandardError => error
      respond(client, 500, { 'ok' => false, 'error' => error.message })
    ensure
      client.close unless client.closed?
    end

    def respond(client, status, payload)
      reason = { 200 => 'OK', 400 => 'Bad Request', 401 => 'Unauthorized', 404 => 'Not Found', 500 => 'Internal Server Error' }.fetch(status, 'Error')
      text = JSON.generate(payload)
      client.write("HTTP/1.1 #{status} #{reason}\r\nContent-Type: application/json\r\nContent-Length: #{text.bytesize}\r\nConnection: close\r\n\r\n#{text}")
    rescue StandardError
      nil
    end

    def schedule_dispatch
      @dispatch_mutex.synchronize do
        return if @dispatch_scheduled
        @dispatch_scheduled = true
      end
      UI.start_timer(0, false) do
        @dispatch_mutex.synchronize { @dispatch_scheduled = false }
        drain_pending
      end
    end

    def drain_pending
      loop do
        request, response_queue = @pending.pop(true)
        response_queue << execute(request)
      rescue ThreadError
        break
      rescue StandardError => error
        response_queue << { 'ok' => false, 'error' => error.message } if response_queue
      end
    end

    def execute(request)
      command = request.fetch('command').to_s
      arguments = request.fetch('arguments', {})
      raise ArgumentError, 'command is not allowed' unless allowed_commands.include?(command)

      case command
      when 'health' then { 'status' => 'ready', 'port' => @port, 'version' => VERSION }
      when 'inspect_model' then inspect_model
      when 'list_tags' then list_tags
      when 'set_tag_visibility' then set_tag_visibility(arguments)
      when 'import_handoff' then import_handoff(arguments)
      when 'place_component' then place_component(arguments)
      when 'save_model_as' then save_model_as(arguments)
      when 'export_preview' then export_preview(arguments)
      when 'quality_check' then quality_check
      end.then { |data| { 'ok' => true, 'data' => data } }
    end

    def safe_path(raw_path, extensions: nil, create_parent: false)
      value = raw_path.to_s.strip
      raise ArgumentError, 'path is required' if value.empty?
      root = File.expand_path(ROOT_PATH)
      absolute = value.match?(/\A(?:[A-Za-z]:[\\\/]|[\\\/])/)
      candidate = absolute ? File.expand_path(value) : File.expand_path(File.join(root, value))
      unless candidate == root || candidate.start_with?(root + File::SEPARATOR)
        raise ArgumentError, "path must stay inside #{root}"
      end
      if extensions && !extensions.any? { |extension| candidate.downcase.end_with?(extension) }
        raise ArgumentError, "unsupported file extension: #{candidate}"
      end
      FileUtils.mkdir_p(File.dirname(candidate)) if create_parent
      candidate
    end

    def inspect_model
      model = Sketchup.active_model
      counts = { 'groups' => 0, 'components' => 0, 'faces' => 0, 'edges' => 0, 'images' => 0 }
      definitions = {}
      walk_entities(model.entities, counts, definitions)
      bounds = model.bounds
      roots = model.entities.grep(Sketchup::Group).filter_map do |group|
        project_id = group.get_attribute(ATTRIBUTE_DICTIONARY, 'project_id')
        next unless project_id
        {
          'name' => group.name,
          'project_id' => project_id,
          'object_count' => group.entities.length,
          'source_sha256' => group.get_attribute(ATTRIBUTE_DICTIONARY, 'source_sha256')
        }
      end
      {
        'title' => model.title,
        'path' => model.path,
        'version' => Sketchup.version,
        'counts' => counts,
        'definition_count' => definitions.length,
        'bounds_m' => [bounds.width.to_f, bounds.height.to_f, bounds.depth.to_f].map { |value| value / (1.m).to_f },
        'tags' => list_tags['tags'],
        'planning_projects' => roots,
        'selection_count' => model.selection.length
      }
    end

    def walk_entities(entities, counts, definitions)
      entities.to_a.each do |entity|
        next unless entity.valid?
        case entity
        when Sketchup::Face then counts['faces'] += 1
        when Sketchup::Edge then counts['edges'] += 1
        when Sketchup::Image then counts['images'] += 1
        when Sketchup::Group
          counts['groups'] += 1
          walk_entities(entity.entities, counts, definitions)
        when Sketchup::ComponentInstance
          counts['components'] += 1
          definition = entity.definition
          next if definitions[definition.object_id]
          definitions[definition.object_id] = true
          walk_entities(definition.entities, counts, definitions)
        end
      end
    end

    def list_tags
      model = Sketchup.active_model
      {
        'tags' => model.layers.to_a.map { |layer| { 'name' => layer.name, 'visible' => layer.visible? } }
      }
    end

    def set_tag_visibility(arguments)
      name = arguments.fetch('name').to_s.strip
      raise ArgumentError, 'tag name is required' if name.empty?
      layer = Sketchup.active_model.layers[name]
      raise ArgumentError, "tag not found: #{name}" unless layer
      visible = !!arguments.fetch('visible')
      model = Sketchup.active_model
      model.start_operation('Planning Toolbox MCP tag visibility', true)
      layer.visible = visible
      model.commit_operation
      { 'name' => name, 'visible' => layer.visible? }
    rescue StandardError
      model.abort_operation if model && model.respond_to?(:abort_operation)
      raise
    end

    def import_handoff(arguments)
      path = safe_path(arguments.fetch('path'), extensions: ['.ptsu.json'])
      counts = PlanningToolbox::SketchUpHandoff.import_handoff_path(path, show_summary: false)
      { 'path' => path, 'counts' => counts.transform_keys(&:to_s) }
    end

    def place_component(arguments)
      asset_id = arguments.fetch('asset_id').to_s
      asset = COMPONENT_ASSETS.fetch(asset_id) { raise ArgumentError, "unknown component: #{asset_id}" }
      point = arguments.fetch('point_m')
      raise ArgumentError, 'point_m must contain x, y, z' unless point.is_a?(Array) && point.length >= 2
      rotation = arguments.fetch('rotation_deg', 0).to_f
      tag = arguments.fetch('tag', 'PT_DETAIL').to_s
      model = Sketchup.active_model
      container = model.entities.grep(Sketchup::Group).find { |group| group.name == 'PT_MCP_COMPONENTS' }
      container ||= model.entities.add_group
      container.name = 'PT_MCP_COMPONENTS'
      object = {
        'sketchup_tag' => tag,
        'procedural_symbol' => {
          'enabled' => true,
          'type' => 'library_component',
          'center_m' => [point[0].to_f, point[1].to_f, (point[2] || 0.0).to_f],
          'rotation_deg' => rotation,
          'component_library' => asset.merge('asset_id' => asset_id)
        }
      }
      counts = Hash.new(0)
      model.start_operation('Planning Toolbox MCP place component', true)
      instance = PlanningToolbox::SketchUpHandoff.add_explicit_library_component(
        model, container.entities, object, counts
      )
      raise ArgumentError, "component could not be loaded: #{asset_id}" unless instance
      instance.set_attribute(ATTRIBUTE_DICTIONARY, 'mcp_created', true)
      instance.set_attribute(ATTRIBUTE_DICTIONARY, 'mcp_asset_id', asset_id)
      model.commit_operation
      { 'asset_id' => asset_id, 'name' => instance.name, 'tag' => tag, 'counts' => counts.transform_keys(&:to_s) }
    rescue StandardError
      model.abort_operation if model && model.respond_to?(:abort_operation)
      raise
    end

    def save_model_as(arguments)
      path = safe_path(arguments.fetch('path'), extensions: ['.skp'], create_parent: true)
      saved = Sketchup.active_model.save(path)
      raise IOError, "SketchUp did not save #{path}" unless saved
      { 'path' => path, 'bytes' => File.size(path) }
    end

    def export_preview(arguments)
      path = safe_path(arguments.fetch('path'), extensions: ['.png', '.jpg', '.jpeg'], create_parent: true)
      view = Sketchup.active_model.active_view
      view.zoom_extents
      options = {
        filename: path,
        width: [[arguments.fetch('width', 1600).to_i, 640].max, 4000].min,
        height: [[arguments.fetch('height', 1000).to_i, 480].max, 4000].min,
        antialias: true,
        compression: 0.9,
        transparent: false
      }
      written = view.write_image(options)
      raise IOError, "SketchUp did not export #{path}" unless written
      { 'path' => path, 'bytes' => File.size(path) }
    end

    def quality_check
      model = Sketchup.active_model
      warnings = []
      roots = model.entities.grep(Sketchup::Group).select do |group|
        group.get_attribute(ATTRIBUTE_DICTIONARY, 'project_id')
      end
      warnings << 'no Planning Toolbox project root found' if roots.empty?
      model.definitions.to_a.each do |definition|
        warnings << "empty component definition: #{definition.name}" if definition.entities.length.zero?
      end
      {
        'status' => warnings.empty? ? 'PASS' : 'WARN',
        'warnings' => warnings,
        'project_root_count' => roots.length,
        'tag_count' => Sketchup.active_model.layers.length
      }
    end
  end
end

module PlanningToolbox
  # The TCP accept thread can otherwise keep a headless SketchUp validation
  # process alive after its model window closes. AppObserver gives the bridge
  # a deterministic shutdown point and releases the port/config file.
  class SketchUpMcpBridgeAppObserver < Sketchup::AppObserver
    def onQuit
      PlanningToolbox::SketchUpMcpBridge.stop!
    end
  end

  def self.install_mcp_bridge_app_observer
    return if defined?(@mcp_bridge_app_observer) && @mcp_bridge_app_observer

    @mcp_bridge_app_observer = SketchUpMcpBridgeAppObserver.new
    Sketchup.add_observer(@mcp_bridge_app_observer)
  end
end

PlanningToolbox.install_mcp_bridge_app_observer
PlanningToolbox::SketchUpMcpBridge.start!
