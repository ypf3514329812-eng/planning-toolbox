# frozen_string_literal: true

# Minimal real-SketchUp acceptance runner for an image-to-CAD-to-SketchUp
# scenario.  It deliberately makes no claims about semantic correctness: it
# imports the exact handoff selected by the caller, records the resulting
# object roles, saves an editable SKP, and writes overview images for review.

require 'json'
require 'fileutils'

handoff_path = ENV.fetch('PT_SKETCHUP_HANDOFF')
validation_dir = ENV.fetch('PT_SKETCHUP_VALIDATION_DIR')
plugin_main = ENV.fetch('PT_SKETCHUP_PLUGIN_MAIN')
report_path = File.join(validation_dir, 'sketchup_runtime_report.json')
model_path = File.join(validation_dir, 'planning_toolbox_siteplan_validation.skp')
axonometric_path = File.join(validation_dir, 'planning_toolbox_siteplan_axonometric.png')
top_path = File.join(validation_dir, 'planning_toolbox_siteplan_top.png')

FileUtils.mkdir_p(validation_dir)

def finish_when_requested
  return unless ENV.fetch('PT_SKETCHUP_AUTO_QUIT', '1') == '1'

  UI.start_timer(1.0, false) { Sketchup.quit }
end

def write_failure(path, stage, error)
  File.write(
    path,
    JSON.pretty_generate(
      'status' => 'FAIL',
      'stage' => stage,
      'error_class' => error.class.name,
      'error_message' => error.message,
      'backtrace' => error.backtrace&.first(20)
    )
  )
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
    roots = model.entities.grep(Sketchup::Group).select do |group|
      group.get_attribute(dictionary, 'project_id')
    end
    raise 'No Planning Toolbox project root was created.' if roots.empty?

    root = roots.first
    # Validation images should show the normal end-user presentation, not
    # SketchUp's optional hidden-geometry debugging view.  Curved road bands
    # deliberately hide their triangulation edges, which otherwise appear as
    # distracting white diagonals in a screenshot inherited from a debug
    # template.
    model.rendering_options['DrawHidden'] = false
    object_groups = root.entities.grep(Sketchup::Group).select do |group|
      group.get_attribute(dictionary, 'object_id')
    end
    role_counts = object_groups.each_with_object(Hash.new(0)) do |group, output|
      output[group.get_attribute(dictionary, 'role').to_s] += 1
    end
    underlay_groups = object_groups.select do |group|
      group.get_attribute(dictionary, 'role') == 'underlay'
    end
    raster_underlay_groups = underlay_groups.select do |group|
      group.get_attribute(dictionary, 'raster_underlay_count', 0).to_i.positive?
    end
    suppressed_road_surface_groups = object_groups.select do |group|
      group.get_attribute(dictionary, 'surface_generation_suppressed', false) == true
    end
    suppressed_road_surface_face_count = suppressed_road_surface_groups.sum do |group|
      group.entities.grep(Sketchup::Face).length
    end
    unless suppressed_road_surface_face_count.zero?
      raise 'Suppressed image-road review outlines unexpectedly contain faces.'
    end
    tag_names = model.layers.map(&:name).grep(/^PT_/).sort
    direct_face_count = object_groups.sum do |group|
      group.entities.grep(Sketchup::Face).length
    end
    direct_edge_count = object_groups.sum do |group|
      group.entities.grep(Sketchup::Edge).length
    end

    bounds = root.bounds
    center = bounds.center
    span = [bounds.width, bounds.height, bounds.depth, 1.0].max
    view = model.active_view
    up = Geom::Vector3d.new(0, 0, 1)
    view.camera = Sketchup::Camera.new(
      Geom::Point3d.new(
        center.x + span * 1.15,
        center.y - span * 1.15,
        center.z + span * 0.90
      ),
      center,
      up
    )
    view.zoom_extents
    view.refresh
    axonometric_status = view.write_image(
      filename: axonometric_path,
      width: 1600,
      height: 1100,
      antialias: true,
      compression: 0.9,
      transparent: false
    )

    view.camera = Sketchup::Camera.new(
      Geom::Point3d.new(center.x, center.y, center.z + span * 3.0),
      center,
      Geom::Vector3d.new(0, 1, 0)
    )
    view.zoom_extents
    view.refresh
    top_status = view.write_image(
      filename: top_path,
      width: 1600,
      height: 1100,
      antialias: true,
      compression: 0.9,
      transparent: false
    )
    save_status = model.save(model_path)

    File.write(
      report_path,
      JSON.pretty_generate(
        'status' => 'PASS',
        'sketchup_version' => Sketchup.version,
        'draw_hidden_geometry' => model.rendering_options['DrawHidden'],
        'handoff_path' => handoff_path,
        'model_path' => model_path,
        'axonometric_path' => axonometric_path,
        'top_path' => top_path,
        'model_save_status' => save_status,
        'axonometric_write_status' => axonometric_status,
        'top_write_status' => top_status,
        'root_group_count' => roots.length,
        'object_group_count' => object_groups.length,
        'role_counts' => role_counts,
        'underlay_group_count' => underlay_groups.length,
        'underlay_locked_count' => underlay_groups.count(&:locked?),
        'raster_underlay_group_count' => raster_underlay_groups.length,
        'raster_image_entity_count' => raster_underlay_groups.sum do |group|
          group.entities.grep(Sketchup::Image).length
        end,
        'suppressed_road_surface_group_count' => suppressed_road_surface_groups.length,
        'suppressed_road_surface_face_count' => suppressed_road_surface_face_count,
        'underlay_source_entity_count' => underlay_groups.sum do |group|
          group.get_attribute(dictionary, 'underlay_source_entity_count', 0).to_i
        end,
        'pt_tags' => tag_names,
        'direct_face_count' => direct_face_count,
        'direct_edge_count' => direct_edge_count,
        'import_counts' => counts.each_with_object({}) do |(key, value), output|
          output[key.to_s] = value
        end
      )
    )
    finish_when_requested
  rescue StandardError => error
    write_failure(report_path, 'image_siteplan_import_or_save', error)
    finish_when_requested
  end
end
