# frozen_string_literal: true

# Real SketchUp integration runner. Launch with SketchUp.exe -RubyStartup.
require 'json'
require 'fileutils'

handoff_path = ENV.fetch('PT_SKETCHUP_HANDOFF')
validation_dir = ENV.fetch('PT_SKETCHUP_VALIDATION_DIR')
plugin_main = File.join(
  ENV.fetch('APPDATA'),
  'SketchUp',
  'SketchUp 2026',
  'SketchUp',
  'Plugins',
  'planning_toolbox_sketchup',
  'main.rb'
)
plugin_main = ENV.fetch('PT_SKETCHUP_PLUGIN_MAIN', plugin_main)
report_path = File.join(validation_dir, 'sketchup_runtime_report.json')
model_path = File.join(validation_dir, 'planning_toolbox_su_validation.skp')
image_path = File.join(validation_dir, 'planning_toolbox_su_validation.png')
road_image_path = File.join(validation_dir, 'planning_toolbox_road_detail.png')

FileUtils.mkdir_p(validation_dir)

def axis_difference_deg(first, second)
  return 180.0 unless first.is_a?(Numeric) && second.is_a?(Numeric)

  difference = (first.to_f - second.to_f).abs % 180.0
  [difference, 180.0 - difference].min
end

def schedule_auto_quit
  return unless ENV['PT_SKETCHUP_AUTO_QUIT'] == '1'

  UI.start_timer(1.0, false) { Sketchup.quit }
end

UI.start_timer(3.0, false) do
  begin
    # SketchUp may auto-load a previously installed user plugin before this
    # runner starts.  For an explicit validation path, always load that exact
    # build so an older installed copy cannot contaminate the evidence.
    if ENV['PT_SKETCHUP_PLUGIN_MAIN'] || !defined?(PlanningToolbox::SketchUpHandoff)
      load(plugin_main)
    end
    # Launching SketchUp with a saved validation model bypasses the welcome
    # screen.  Immediately switch to a clean model so that prior evidence is
    # never modified or mixed into the current run.
    Sketchup.file_new
    counts = PlanningToolbox::SketchUpHandoff.import_handoff_path(
      handoff_path,
      show_summary: false
    )
    model = Sketchup.active_model
    dictionary = PlanningToolbox::SketchUpHandoff::ATTRIBUTE_DICTIONARY
    roots = model.entities.grep(Sketchup::Group).select do |group|
      group.get_attribute(dictionary, 'project_id')
    end
    raise '没有生成 Planning Toolbox 项目根分组。' if roots.empty?

    root = roots.first
    object_groups = root.entities.grep(Sketchup::Group).select do |group|
      group.get_attribute(dictionary, 'object_id')
    end
    building_groups = object_groups.select do |group|
      group.get_attribute(dictionary, 'role') == 'building'
    end
    road_groups = object_groups.select do |group|
      group.get_attribute(dictionary, 'role') == 'road'
    end
    buildings = building_groups.map do |group|
      {
        'name' => group.name,
        'object_id' => group.get_attribute(dictionary, 'object_id'),
        'source_handle' => group.get_attribute(dictionary, 'source_handle'),
        'height_m' => (group.bounds.depth.to_f / 39.37007874015748).round(3),
        'face_count' => group.entities.grep(Sketchup::Face).length,
        'edge_count' => group.entities.grep(Sketchup::Edge).length,
        'detail_group_count' => group.entities.grep(Sketchup::Group).count do |child|
          child.get_attribute(dictionary, 'generated_detail', false)
        end
      }
    end
    tag_names = model.layers.map(&:name).grep(/^PT_/).sort
    facade_definitions = model.definitions.count do |definition|
      definition.get_attribute(dictionary, 'component_role') == 'facade_window'
    end
    tree_definitions = model.definitions.count do |definition|
      definition.get_attribute(dictionary, 'component_role') == 'site_tree'
    end
    library_definitions = model.definitions.filter_map do |definition|
      asset_id = definition.get_attribute(dictionary, 'component_asset_id')
      next unless asset_id

      {
        'asset_id' => asset_id,
        'source_id' => definition.get_attribute(dictionary, 'component_source_id'),
        'license' => definition.get_attribute(dictionary, 'component_license'),
        'instance_count' => definition.instances.length
      }
    end
    crosswalk_instances = object_groups.flat_map do |group|
      group.entities.grep(Sketchup::ComponentInstance)
    end.select do |instance|
      instance.get_attribute(dictionary, 'component_asset_id') == 'road_crossing'
    end
    raise '没有生成斑马线组件。' if crosswalk_instances.empty?

    curved_street_light_instances = object_groups.flat_map do |group|
      group.entities.grep(Sketchup::ComponentInstance)
    end.select do |instance|
      instance.get_attribute(dictionary, 'component_asset_id') == 'street_light' &&
        instance.get_attribute(dictionary, 'road_geometry') == 'curved_local_tangent'
    end

    crosswalks = crosswalk_instances.map do |instance|
      y_axis = instance.transformation.yaxis
      bar_axis_deg = Math.atan2(y_axis.y, y_axis.x) * 180.0 / Math::PI
      marking_group = instance.definition.entities.grep(Sketchup::Group).find do |group|
        group.name == 'PT_CROSSWALK_MARKINGS'
      end
      marking_faces = marking_group ? marking_group.entities.grep(Sketchup::Face) : []
      {
        'name' => instance.name,
        'rotation_deg' => instance.get_attribute(dictionary, 'rotation_deg'),
        'bar_axis_deg' => (bar_axis_deg % 180.0).round(3),
        'cad_rotation_deg' => instance.get_attribute(dictionary, 'cad_rotation_deg'),
        'orientation_source' => instance.get_attribute(dictionary, 'orientation_source'),
        'matched_road_id' => instance.get_attribute(dictionary, 'matched_road_id'),
        'matched_road_axis_deg' => instance.get_attribute(dictionary, 'matched_road_axis_deg'),
        'orientation_confidence' => instance.get_attribute(dictionary, 'orientation_confidence'),
        'marking_face_count' => marking_faces.length,
        'marking_materials' => marking_faces.map { |face| face.material&.name }.uniq,
        'marking_centers' => marking_faces.map do |face|
          [
            (face.bounds.center.x.to_f / 1.m.to_f).round(4),
            (face.bounds.center.y.to_f / 1.m.to_f).round(4),
            (face.bounds.center.z.to_f / 1.m.to_f).round(4)
          ]
        end,
        'marking_normals' => marking_faces.map do |face|
          [face.normal.x.round(3), face.normal.y.round(3), face.normal.z.round(3)]
        end,
        'marking_hidden' => marking_faces.map(&:hidden?),
        'width_m' => (instance.bounds.width.to_f / 1.m.to_f).round(3),
        'depth_m' => (instance.bounds.height.to_f / 1.m.to_f).round(3),
        'height_m' => (instance.bounds.depth.to_f / 1.m.to_f).round(3)
      }
    end
    unless crosswalks.all? do |item|
      %w[matched_road_long_axis matched_road_local_tangent].include?(item['orientation_source'])
    end
      raise '斑马线没有使用可信道路方向完成自动校正。'
    end
    unless crosswalks.all? do |item|
      axis_difference_deg(item['bar_axis_deg'], item['matched_road_axis_deg']) <= 0.5
    end
      raise '斑马线长条没有与匹配道路的车行方向保持平行。'
    end
    if ENV['PT_EXPECT_CURVED_ROAD'] == '1'
      raise '没有生成弯道局部道路细化面。' unless counts[:road_curved_surfaces].to_i.positive?
      raise '弯道细化没有生成分段面。' unless counts[:road_curved_detail_faces].to_i.positive?
      raise '弯道没有生成道路边线。' unless counts[:road_curved_edge_lines].to_i.positive?
      raise '弯道没有生成中心虚线。' unless counts[:lane_markings].to_i.positive?
      raise '弯道没有沿局部切线生成街灯。' unless counts[:road_curved_street_lights].to_i.positive?
      unless curved_street_light_instances.length == counts[:road_curved_street_lights].to_i
        raise '弯道街灯缺少局部切线元数据。'
      end
    end
    if ENV['PT_EXPECT_ROUNDABOUT'] == '1'
      raise '没有生成环岛环带面。' unless counts[:road_roundabout_surfaces].to_i.positive?
      raise '环岛没有生成分段道路面。' unless counts[:road_roundabout_detail_faces].to_i.positive?
      raise '环岛没有生成道路边线。' unless counts[:road_roundabout_edge_lines].to_i.positive?
      raise '环岛不应生成直行中心虚线。' if counts[:lane_markings].to_i.positive?
      roundabout_roads = road_groups.select do |group|
        group.entities.grep(Sketchup::Face).length >= counts[:road_roundabout_detail_faces].to_i
      end
      raise '环岛道路组未保留环带面。' if roundabout_roads.empty?
    end
    if ENV['PT_EXPECT_CENTERLINE_CORRIDOR'] == '1'
      raise '中心线没有生成概念道路带面。' unless counts[:road_centerline_corridor_surfaces].to_i.positive?
      raise '中心线道路带没有生成分段细化面。' unless counts[:road_centerline_corridor_faces].to_i.positive?
      raise '中心线道路带没有生成道路边线。' unless counts[:road_curved_edge_lines].to_i.positive?
      raise '中心线道路带没有生成中心虚线。' unless counts[:lane_markings].to_i.positive?
      raise '中心线道路带没有生成沿局部切线的街灯。' unless counts[:road_curved_street_lights].to_i.positive?
      corridor_roads = road_groups.select do |group|
        group.entities.grep(Sketchup::Face).length >= counts[:road_centerline_corridor_faces].to_i
      end
      raise '中心线道路组没有保留可编辑道路面。' if corridor_roads.empty?
    end
    detail_definition_counts = %w[
      building_entrance entrance_canopy residential_balcony rooftop_equipment
    ].each_with_object({}) do |role, output|
      output[role] = model.definitions.count do |definition|
        definition.get_attribute(dictionary, 'component_role') == role
      end
    end

    view = model.active_view
    view.camera = Sketchup::Camera.new(
      Geom::Point3d.new(135.m, -120.m, 90.m),
      Geom::Point3d.new(45.m, 35.m, 12.m),
      Geom::Vector3d.new(0, 0, 1)
    )
    view.zoom_extents
    view.refresh

    UI.start_timer(2.0, false) do
      begin
        save_status = model.save(model_path)
        image_status = view.write_image(
          filename: image_path,
          width: 1600,
          height: 1000,
          antialias: true,
          compression: 0.9,
          transparent: false
        )
        view.camera = Sketchup::Camera.new(
          Geom::Point3d.new(28.m, -72.m, 44.m),
          Geom::Point3d.new(28.m, 13.m, 0.m),
          Geom::Vector3d.new(0, 0, 1)
        )
        view.refresh
        road_image_status = view.write_image(
          filename: road_image_path,
          width: 1600,
          height: 1000,
          antialias: true,
          compression: 0.9,
          transparent: false
        )
        report = {
          'status' => 'PASS',
          'sketchup_version' => Sketchup.version,
          'sketchup_version_number' => Sketchup.version_number,
          'plugin_version' => '0.26.0',
          'handoff_path' => handoff_path,
          'model_path' => model_path,
          'image_path' => image_path,
          'road_image_path' => road_image_path,
          'model_save_status' => save_status,
          'image_write_status' => image_status,
          'road_image_write_status' => road_image_status,
          'root_group_count' => roots.length,
          'object_group_count' => object_groups.length,
          'building_group_count' => building_groups.length,
          'road_group_count' => road_groups.length,
          'roads' => road_groups.map do |group|
            {
              'name' => group.name,
              'width_m' => (group.bounds.width.to_f / 1.m.to_f).round(3),
              'depth_m' => (group.bounds.height.to_f / 1.m.to_f).round(3),
              'height_m' => (group.bounds.depth.to_f / 1.m.to_f).round(3),
              'face_count' => group.entities.grep(Sketchup::Face).length,
              'edge_count' => group.entities.grep(Sketchup::Edge).length
            }
          end,
          'buildings' => buildings,
          'pt_tags' => tag_names,
          'facade_definition_count' => facade_definitions,
          'tree_definition_count' => tree_definitions,
          'library_definitions' => library_definitions,
          'crosswalks' => crosswalks,
          'curved_road_detail_counts' => {
            'surfaces' => counts[:road_curved_surfaces].to_i,
            'sidewalk_faces' => counts[:road_curved_sidewalk_faces].to_i,
            'edge_lines' => counts[:road_curved_edge_lines].to_i,
            'detail_faces' => counts[:road_curved_detail_faces].to_i,
            'lane_markings' => counts[:lane_markings].to_i,
            'direction_arrows' => counts[:road_direction_arrows].to_i,
            'street_lights' => counts[:road_curved_street_lights].to_i,
            'street_light_instances' => curved_street_light_instances.map do |instance|
              {
                'station_m' => instance.get_attribute(dictionary, 'road_local_station_m'),
                'axis_deg' => instance.get_attribute(dictionary, 'road_local_axis_deg'),
                'side' => instance.get_attribute(dictionary, 'road_side')
              }
            end
          },
          'roundabout_detail_counts' => {
            'surfaces' => counts[:road_roundabout_surfaces].to_i,
            'detail_faces' => counts[:road_roundabout_detail_faces].to_i,
            'sidewalk_faces' => counts[:road_roundabout_sidewalk_faces].to_i,
            'edge_lines' => counts[:road_roundabout_edge_lines].to_i,
            'center_marking_suppressed' => counts[:road_roundabout_center_marking_suppressed].to_i
          },
          'centerline_corridor_detail_counts' => {
            'surfaces' => counts[:road_centerline_corridor_surfaces].to_i,
            'detail_faces' => counts[:road_centerline_corridor_faces].to_i,
            'edge_lines' => counts[:road_curved_edge_lines].to_i,
            'lane_markings' => counts[:lane_markings].to_i,
            'street_lights' => counts[:road_curved_street_lights].to_i
          },
          'detail_definition_counts' => detail_definition_counts,
          'import_counts' => counts.each_with_object({}) do |(key, value), output|
            output[key.to_s] = value
          end
        }
        File.write(report_path, JSON.pretty_generate(report))
        Sketchup.status_text = 'Planning Toolbox 真实 SketchUp 验收通过。'
        schedule_auto_quit
      rescue StandardError => error
        File.write(
          report_path,
          JSON.pretty_generate(
            'status' => 'FAIL',
            'stage' => 'save_or_image',
            'error_class' => error.class.name,
            'error_message' => error.message,
            'backtrace' => error.backtrace&.first(20)
          )
        )
        schedule_auto_quit
      end
    end
  rescue StandardError => error
    File.write(
      report_path,
      JSON.pretty_generate(
        'status' => 'FAIL',
        'stage' => 'import_or_inspection',
        'error_class' => error.class.name,
        'error_message' => error.message,
        'backtrace' => error.backtrace&.first(20)
      )
    )
    schedule_auto_quit
  end
end
