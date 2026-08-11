# frozen_string_literal: true

# Minimal SketchUp RubyStartup probe used only for local integration diagnostics.
# It deliberately writes a fixed project-scoped marker and exits SketchUp.
require 'time'

probe_root = ENV.fetch('PLANNING_TOOLBOX_ROOT', Dir.tmpdir)
probe_path = File.join(probe_root, 'test_artifacts', 'sketchup_runtime_probe.txt')
File.open(probe_path, 'w') do |file|
  file.write("SketchUp RubyStartup reached\n")
  file.write("version=#{Sketchup.version}\n") if defined?(Sketchup)
  file.write("time=#{Time.now.utc.iso8601}\n")
end

UI.start_timer(2.0, false) { Sketchup.quit }
