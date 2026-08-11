# frozen_string_literal: true

# Convert a small audited CC0 GLB selection into native SKP component files.
# Launch with SketchUp.exe -RubyStartup and the environment variables below.
require 'json'
require 'fileutils'

source_dir = ENV.fetch('PT_COMPONENT_SOURCE_DIR')
output_dir = ENV.fetch('PT_COMPONENT_OUTPUT_DIR')
report_path = ENV.fetch('PT_COMPONENT_REPORT')

assets = [
  ['tree_large', 'kenney_cc0/suburban_tree-large.glb', 'pt_tree_large.skp', 'vegetation_tree_large', 'Kenney', 'kenney-city-kit-suburban-2.0'],
  ['tree_small', 'kenney_cc0/suburban_tree-small.glb', 'pt_tree_small.skp', 'vegetation_tree_small', 'Kenney', 'kenney-city-kit-suburban-2.0'],
  ['planter', 'kenney_cc0/suburban_planter.glb', 'pt_planter.skp', 'site_planter', 'Kenney', 'kenney-city-kit-suburban-2.0'],
  ['street_light', 'kenney_cc0/roads_light-curved.glb', 'pt_street_light.skp', 'street_light', 'Kenney', 'kenney-city-kit-roads-2.0'],
  ['awning_wide', 'kenney_cc0/commercial_detail-awning-wide.glb', 'pt_awning_wide.skp', 'entrance_awning', 'Kenney', 'kenney-city-kit-commercial-2.1'],
  ['overhang_wide', 'kenney_cc0/commercial_detail-overhang-wide.glb', 'pt_overhang_wide.skp', 'entrance_overhang', 'Kenney', 'kenney-city-kit-commercial-2.1'],
  ['parasol', 'kenney_cc0/commercial_detail-parasol-a.glb', 'pt_parasol.skp', 'site_parasol', 'Kenney', 'kenney-city-kit-commercial-2.1'],
  ['road_crossing', 'kaykit_cc0/kaykit_road_straight_crossing.glb', 'pt_road_crossing.skp', 'road_crossing', 'Kay Lousberg', 'kaykit-city-builder-bits-1.0'],
  ['traffic_light', 'kaykit_cc0/kaykit_trafficlight_A.glb', 'pt_traffic_light.skp', 'traffic_light', 'Kay Lousberg', 'kaykit-city-builder-bits-1.0']
].freeze

FileUtils.mkdir_p(output_dir)

UI.start_timer(3.0, false) do
  records = []
  begin
    assets.each do |asset_id, source_name, output_name, role, creator, source_id|
      source_path = File.join(source_dir, source_name)
      output_path = File.join(output_dir, output_name)
      raise "缺少组件源文件：#{source_path}" unless File.file?(source_path)

      Sketchup.file_new
      model = Sketchup.active_model
      # A new SketchUp template may contain the default scale figure.  Remove
      # all template entities before import so component bounds and scaling are
      # based only on the audited asset.
      template_entities = model.entities.to_a
      model.entities.erase_entities(template_entities) unless template_entities.empty?
      model.definitions.purge_unused
      model.materials.purge_unused
      imported = model.import(source_path)
      raise "SketchUp 无法导入组件：#{source_name}" unless imported

      bounds = model.bounds
      raise "组件导入后没有有效几何：#{source_name}" if bounds.empty?

      model.set_attribute('PlanningToolboxAsset', 'asset_id', asset_id)
      model.set_attribute('PlanningToolboxAsset', 'role', role)
      model.set_attribute('PlanningToolboxAsset', 'source_license', 'CC0-1.0')
      model.set_attribute('PlanningToolboxAsset', 'source_creator', creator)
      model.set_attribute('PlanningToolboxAsset', 'source_id', source_id)
      saved = model.save(output_path)
      raise "组件保存失败：#{output_name}" unless saved

      records << {
        'asset_id' => asset_id,
        'role' => role,
        'source_id' => source_id,
        'source_creator' => creator,
        'source_path' => source_path,
        'output_path' => output_path,
        'import_status' => imported,
        'save_status' => saved,
        'root_entity_count' => model.entities.length,
        'definition_count' => model.definitions.length,
        'bounds_m' => {
          'width' => (bounds.width.to_f / 1.m.to_f).round(4),
          'depth' => (bounds.height.to_f / 1.m.to_f).round(4),
          'height' => (bounds.depth.to_f / 1.m.to_f).round(4)
        },
        'size_bytes' => File.size(output_path)
      }
    end
    File.write(
      report_path,
      JSON.pretty_generate(
        'status' => 'PASS',
        'sketchup_version' => Sketchup.version,
        'asset_count' => records.length,
        'assets' => records
      )
    )
    Sketchup.status_text = 'Planning Toolbox CC0 组件转换完成。'
  rescue StandardError => error
    File.write(
      report_path,
      JSON.pretty_generate(
        'status' => 'FAIL',
        'error_class' => error.class.name,
        'error_message' => error.message,
        'completed_assets' => records,
        'backtrace' => error.backtrace&.first(20)
      )
    )
  end
end
