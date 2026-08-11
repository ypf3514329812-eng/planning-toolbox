# frozen_string_literal: true

require 'json'
require 'fileutils'

handoff_path = ENV.fetch('PT_SKETCHUP_HANDOFF')
validation_dir = ENV.fetch('PT_SKETCHUP_VALIDATION_DIR')
plugin_main = ENV.fetch('PT_SKETCHUP_PLUGIN_MAIN')
report_path = File.join(validation_dir, 'sketchup_native_component_report.json')
model_path = File.join(validation_dir, 'native_component_validation.skp')
image_path = File.join(validation_dir, 'native_component_validation.png')
FileUtils.mkdir_p(validation_dir)

def planning_component_instances(entities)
  entities.each_with_object([]) do |entity, result|
    if entity.is_a?(Sketchup::ComponentInstance)
      result << entity
    elsif entity.is_a?(Sketchup::Group)
      result.concat(planning_component_instances(entity.entities))
    end
  end
end

UI.start_timer(3.0, false) do
  begin
    load(plugin_main)
    Sketchup.file_new
    counts = PlanningToolbox::SketchUpHandoff.import_handoff_path(
      handoff_path,
      show_summary: false
    )
    model = Sketchup.active_model
    dictionary = PlanningToolbox::SketchUpHandoff::ATTRIBUTE_DICTIONARY
    instances = planning_component_instances(model.entities)
    component_instances = instances.select do |instance|
      instance.get_attribute(dictionary, 'component_asset_id')
    end
    expected = %w[parked_car bench shrub_cluster bollard bus_shelter]
    observed = component_instances.map do |instance|
      instance.get_attribute(dictionary, 'component_asset_id')
    end
    missing = expected - observed
    raise "缺少原生规划组件：#{missing.join(', ')}" unless missing.empty?

    definitions = component_instances.map(&:definition).uniq
    native_definitions = definitions.select do |definition|
      definition.get_attribute(dictionary, 'component_origin') == 'native_generator'
    end
    raise '原生组件没有共享 SketchUp 定义。' unless native_definitions.length == expected.length
    raise '原生组件没有产生有效几何。' if native_definitions.any? { |definition| definition.bounds.empty? }

    view = model.active_view
    view.camera = Sketchup::Camera.new(
      Geom::Point3d.new(52.m, -62.m, 58.m),
      Geom::Point3d.new(36.m, 18.m, 0.m),
      Geom::Vector3d.new(0, 0, 1)
    )
    view.zoom_extents
    view.refresh
    UI.start_timer(1.5, false) do
      save_status = model.save(model_path)
      image_status = view.write_image(
        filename: image_path,
        width: 1600,
        height: 1000,
        antialias: true,
        compression: 0.9,
        transparent: false
      )
      File.write(
        report_path,
        JSON.pretty_generate(
          'status' => 'PASS',
          'counts' => counts,
          'expected_assets' => expected,
          'observed_assets' => observed,
          'native_definition_count' => native_definitions.length,
          'component_instance_count' => component_instances.length,
          'model_path' => model_path,
          'image_path' => image_path,
          'model_size_bytes' => File.size(model_path),
          'image_size_bytes' => File.size(image_path),
          'save_status' => save_status,
          'image_status' => image_status
        )
      )
      UI.start_timer(1.0, false) { Sketchup.quit }
    end
  rescue StandardError => error
    File.write(
      report_path,
      JSON.pretty_generate(
        'status' => 'FAIL',
        'error_class' => error.class.name,
        'error_message' => error.message,
        'backtrace' => error.backtrace&.first(20)
      )
    )
    UI.start_timer(1.0, false) { Sketchup.quit }
  end
end
