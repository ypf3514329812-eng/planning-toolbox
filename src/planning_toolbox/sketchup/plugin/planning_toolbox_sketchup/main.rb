# frozen_string_literal: true

require 'sketchup.rb'
require 'json'
require 'digest'

module PlanningToolbox
  module SketchUpHandoff
    FORMAT = 'planning-toolbox-sketchup-handoff'
    SCHEMA_VERSION = 7
    SUPPORTED_SCHEMA_VERSIONS = [1, 2, 3, 4, 5, 6, 7].freeze
    ATTRIBUTE_DICTIONARY = 'Planning Toolbox'
    COMPONENT_DIR = File.join(__dir__, 'components')
    USER_COMPONENT_DIR = File.join(
      ENV.fetch('APPDATA', __dir__),
      'PlanningToolbox',
      'SketchUpComponents'
    )
    MATERIALS = {
      'building' => ['PT 建筑', [197, 176, 147], 1.0],
      'parcel' => ['PT 地块', [240, 236, 226], 0.35],
      'green' => ['PT 绿地', [151, 174, 148], 0.75],
      'road' => ['PT 道路', [184, 184, 178], 0.8],
      'water' => ['PT 水体', [139, 172, 183], 0.7],
      'parking' => ['PT 停车', [203, 190, 164], 0.75],
      'other' => ['PT 其他', [215, 211, 202], 0.5]
    }.freeze

    module_function

    def load_json(path)
      text = File.open(path, 'r:bom|utf-8', &:read)
      data = JSON.parse(text)
      supported = SUPPORTED_SCHEMA_VERSIONS.include?(data['schema_version'].to_i)
      unless data['format'] == FORMAT && supported
        raise ArgumentError, '这不是当前版本支持的 Planning Toolbox SketchUp 交接文件。'
      end
      objects = data['objects']
      unless objects.is_a?(Array) && !objects.empty?
        raise ArgumentError, '交接文件中没有可生成的 CAD 对象。'
      end

      data
    end

    def material_for(model, role)
      name, rgb, alpha = MATERIALS.fetch(role, MATERIALS['other'])
      material = model.materials[name] || model.materials.add(name)
      material.color = Sketchup::Color.new(*rgb)
      material.alpha = alpha
      material
    end

    def window_material(model)
      material = model.materials['PT 窗玻璃'] || model.materials.add('PT 窗玻璃')
      material.color = Sketchup::Color.new(126, 157, 168)
      material.alpha = 0.72
      material
    end

    def roof_material(model)
      material = model.materials['PT 屋顶'] || model.materials.add('PT 屋顶')
      material.color = Sketchup::Color.new(170, 148, 128)
      material.alpha = 1.0
      material
    end

    def tree_canopy_material(model)
      material = model.materials['PT Tree Canopy'] || model.materials.add('PT Tree Canopy')
      material.color = Sketchup::Color.new(116, 151, 112)
      material.alpha = 0.92
      material
    end

    def tree_trunk_material(model)
      material = model.materials['PT Tree Trunk'] || model.materials.add('PT Tree Trunk')
      material.color = Sketchup::Color.new(139, 111, 83)
      material.alpha = 1.0
      material
    end

    def detail_material(model, key)
      presets = {
        'door_frame' => ['PT Door Frame', [72, 79, 82], 1.0],
        'door_glass' => ['PT Door Glass', [101, 145, 160], 0.76],
        'metal' => ['PT Architectural Metal', [158, 160, 158], 1.0],
        'plinth' => ['PT Building Plinth', [137, 128, 117], 1.0],
        'road_component' => ['PT Road Component', [172, 173, 169], 1.0],
        'curb' => ['PT Road Curb', [214, 212, 204], 1.0],
        'sidewalk' => ['PT Road Sidewalk', [202, 197, 185], 1.0],
        'marking' => ['PT Parking Marking', [245, 244, 234], 1.0],
        'bank' => ['PT Water Bank', [116, 142, 145], 1.0],
        'edging' => ['PT Green Edging', [111, 135, 108], 1.0],
        'equipment' => ['PT Rooftop Equipment', [151, 154, 151], 1.0],
        'site_furniture' => ['PT Site Furniture', [92, 101, 102], 1.0],
        'canopy' => ['PT Entrance Canopy', [117, 139, 145], 1.0],
        'parasol' => ['PT Site Parasol', [207, 190, 158], 1.0]
      }
      name, rgb, alpha = presets.fetch(key, presets['metal'])
      material = model.materials[name] || model.materials.add(name)
      material.color = Sketchup::Color.new(*rgb)
      material.alpha = alpha
      material
    end

    def building_type_material(model, building_type, knowledge_rgb = nil)
      presets = {
        'residential' => ['PT Building Residential', [202, 184, 158]],
        'office' => ['PT Building Office', [184, 193, 195]],
        'commercial' => ['PT Building Commercial', [211, 188, 151]],
        'campus' => ['PT Building Campus', [190, 161, 141]],
        'generic' => ['PT Building Generic', [197, 176, 147]]
      }
      name, rgb = presets.fetch(building_type, presets['generic'])
      if knowledge_rgb.is_a?(Array) && knowledge_rgb.length == 3 &&
         knowledge_rgb.all? { |value| value.is_a?(Numeric) && value.between?(0, 255) }
        rgb = knowledge_rgb.map(&:to_i)
      end
      material = model.materials[name] || model.materials.add(name)
      material.color = Sketchup::Color.new(*rgb)
      material.alpha = 1.0
      material
    end

    def points_from_metres(raw_points)
      raw_points.map do |point|
        Geom::Point3d.new(point[0].to_f.m, point[1].to_f.m, point[2].to_f.m)
      end
    end

    def component_palette_material(model, asset_id, height_ratio)
      case asset_id
      when 'tree_large', 'tree_small'
        height_ratio < 0.32 ? tree_trunk_material(model) : tree_canopy_material(model)
      when 'planter'
        height_ratio < 0.55 ? detail_material(model, 'plinth') : tree_canopy_material(model)
      when 'parasol'
        height_ratio > 0.48 ? detail_material(model, 'parasol') : detail_material(model, 'site_furniture')
      when 'street_light'
        detail_material(model, 'site_furniture')
      when 'awning_wide', 'overhang_wide'
        detail_material(model, 'canopy')
      when 'road_crossing'
        detail_material(model, 'road_component')
      end
    end

    def native_material(model, name, rgb, alpha = 1.0)
      material = model.materials[name] || model.materials.add(name)
      material.color = Sketchup::Color.new(*rgb)
      material.alpha = alpha
      material
    end

    def native_paint_new_faces(entities, before_faces, material)
      (entities.grep(Sketchup::Face) - before_faces).each do |face|
        face.material = material
        face.back_material = material
      end
    end

    def native_box(entities, x, y, z, width, depth, height, material)
      before = entities.grep(Sketchup::Face)
      points = [
        Geom::Point3d.new(x.m, y.m, z.m),
        Geom::Point3d.new((x + width).m, y.m, z.m),
        Geom::Point3d.new((x + width).m, (y + depth).m, z.m),
        Geom::Point3d.new(x.m, (y + depth).m, z.m)
      ]
      face = entities.add_face(points)
      return unless face

      face.reverse! if face.normal.z < 0
      face.pushpull(height.m)
      native_paint_new_faces(entities, before, material)
    end

    def native_cylinder(entities, x, y, z, radius, height, material, normal = Z_AXIS, segments = 10)
      before = entities.grep(Sketchup::Face)
      edges = entities.add_circle(
        Geom::Point3d.new(x.m, y.m, z.m),
        normal,
        radius.m,
        segments
      )
      face = entities.add_face(edges)
      return unless face

      face.pushpull(height.m)
      native_paint_new_faces(entities, before, material)
    end

    def native_cone(entities, x, y, z, radius, height, material, top_ratio = 0.35, segments = 8)
      before = entities.grep(Sketchup::Face)
      bottom = (0...segments).map do |index|
        angle = 2.0 * Math::PI * index / segments.to_f
        Geom::Point3d.new((x + Math.cos(angle) * radius).m,
                          (y + Math.sin(angle) * radius).m,
                          z.m)
      end
      top = (0...segments).map do |index|
        angle = 2.0 * Math::PI * index / segments.to_f
        Geom::Point3d.new((x + Math.cos(angle) * radius * top_ratio).m,
                          (y + Math.sin(angle) * radius * top_ratio).m,
                          (z + height).m)
      end
      entities.add_face(bottom.reverse)
      entities.add_face(top)
      segments.times do |index|
        entities.add_face([bottom[index], bottom[(index + 1) % segments],
                           top[(index + 1) % segments], top[index]])
      end
      native_paint_new_faces(entities, before, material)
    end

    def native_parked_car(model, definition)
      body = native_material(model, 'PT Vehicle Body', [87, 103, 111])
      trim = native_material(model, 'PT Vehicle Trim', [48, 54, 57])
      glass = native_material(model, 'PT Vehicle Glass', [105, 143, 153], 0.78)
      lamp = native_material(model, 'PT Vehicle Lamp', [226, 188, 121])
      native_box(definition.entities, -2.25, -0.82, 0.38, 4.5, 1.64, 0.55, body)
      native_box(definition.entities, -1.15, -0.68, 0.93, 2.35, 1.36, 0.38, body)
      native_box(definition.entities, -0.97, -0.695, 1.0, 0.82, 0.025, 0.30, glass)
      native_box(definition.entities, 0.10, -0.695, 1.0, 0.82, 0.025, 0.30, glass)
      native_box(definition.entities, -0.97, 1.0, 1.0, 0.82, 0.025, 0.30, glass)
      native_box(definition.entities, 0.10, 1.0, 1.0, 0.82, 0.025, 0.30, glass)
      native_box(definition.entities, -2.26, -0.58, 0.55, 0.08, 1.16, 0.18, lamp)
      native_box(definition.entities, 2.18, -0.58, 0.55, 0.08, 1.16, 0.18, lamp)
      [-1.45, 1.45].each do |x|
        native_cylinder(definition.entities, x, -0.92, 0.28, 0.34, 0.18, trim, Y_AXIS, 12)
        native_cylinder(definition.entities, x, 0.74, 0.28, 0.34, 0.18, trim, Y_AXIS, 12)
      end
      definition.entities.grep(Sketchup::Edge).each { |edge| edge.soft = true if edge.faces.length == 2 }
    end

    def native_bench(model, definition)
      wood = native_material(model, 'PT Bench Wood', [157, 121, 83])
      metal = native_material(model, 'PT Bench Metal', [83, 91, 91])
      3.times do |index|
        native_box(definition.entities, -0.9, -0.30 + index * 0.20, 0.52, 1.8, 0.16, 0.10, wood)
      end
      2.times do |index|
        x = -0.72 + index * 1.44
        native_box(definition.entities, x, -0.27, 0.0, 0.10, 0.54, 0.52, metal)
        native_box(definition.entities, x, -0.25, 0.96, 0.10, 0.10, 0.72, metal)
      end
      3.times do |index|
        native_box(definition.entities, -0.9, 0.22 + index * 0.18, 0.88, 1.8, 0.12, 0.10, wood)
      end
    end

    def native_shrub_cluster(model, definition)
      dark = native_material(model, 'PT Shrub Dark', [86, 121, 82])
      light = native_material(model, 'PT Shrub Light', [129, 157, 93])
      native_cone(definition.entities, -0.62, 0.05, 0.0, 0.62, 1.15, dark, 0.42, 8)
      native_cone(definition.entities, 0.15, -0.05, 0.0, 0.72, 1.35, light, 0.38, 8)
      native_cone(definition.entities, 0.78, 0.18, 0.0, 0.48, 0.92, dark, 0.40, 8)
    end

    def native_bollard(model, definition)
      metal = native_material(model, 'PT Bollard Metal', [76, 83, 83])
      band = native_material(model, 'PT Bollard Band', [224, 190, 104])
      native_cylinder(definition.entities, 0.0, 0.0, 0.0, 0.16, 0.10, metal, Z_AXIS, 10)
      native_cylinder(definition.entities, 0.0, 0.0, 0.10, 0.09, 0.80, metal, Z_AXIS, 10)
      native_cylinder(definition.entities, 0.0, 0.0, 0.58, 0.095, 0.10, band, Z_AXIS, 10)
      native_cylinder(definition.entities, 0.0, 0.0, 0.90, 0.12, 0.10, metal, Z_AXIS, 10)
    end

    def native_bus_shelter(model, definition)
      metal = native_material(model, 'PT Bus Shelter Metal', [77, 86, 87])
      glass = native_material(model, 'PT Bus Shelter Glass', [136, 170, 178], 0.45)
      roof = native_material(model, 'PT Bus Shelter Roof', [155, 139, 111])
      wood = native_material(model, 'PT Bus Shelter Seat', [153, 119, 82])
      native_box(definition.entities, -2.0, -0.8, 3.0, 4.0, 1.6, 0.16, roof)
      [-1.75, 1.60].each do |x|
        native_box(definition.entities, x, -0.68, 0.0, 0.12, 0.12, 3.0, metal)
        native_box(definition.entities, x, 0.56, 0.0, 0.12, 0.12, 3.0, metal)
      end
      native_box(definition.entities, -1.60, 0.42, 0.55, 3.2, 0.05, 1.9, glass)
      native_box(definition.entities, -1.50, -0.55, 0.52, 3.0, 0.55, 0.12, wood)
      native_box(definition.entities, -1.30, -0.35, 0.64, 2.6, 0.08, 0.55, wood)
    end

    def native_component_definition(model, asset, counts)
      asset_id = asset['asset_id'].to_s
      generator = asset['native_generator'].to_s
      cached = model.definitions.find do |definition|
        definition.get_attribute(ATTRIBUTE_DICTIONARY, 'component_asset_id') == asset_id
      end
      return cached if cached

      definition = model.definitions.add("PT_NATIVE_#{asset_id.upcase}")
      case generator
      when 'parked_car' then native_parked_car(model, definition)
      when 'bench' then native_bench(model, definition)
      when 'shrub_cluster' then native_shrub_cluster(model, definition)
      when 'bollard' then native_bollard(model, definition)
      when 'bus_shelter' then native_bus_shelter(model, definition)
      else
        definition.entities.erase_entities(definition.entities.to_a)
      end
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_asset_id', asset_id)
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_source_id', asset['source_id'])
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_license', asset['license'])
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_origin', 'native_generator')
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_generator', generator)
      counts[:library_definitions_loaded] += 1
      definition
    rescue StandardError
      nil
    end

    def add_road_crossing_markings(definition, model, settings = {}, source_bounds = nil)
      bounds = source_bounds || definition.bounds
      return if bounds.empty?

      marking = detail_material(model, 'marking')
      stripe_count = [[settings.fetch('stripe_count', 7).to_i, 3].max, 19].min
      stripe_half_width_fraction = [
        [settings.fetch('stripe_half_width_fraction', 0.045).to_f, 0.01].max,
        0.12
      ].min
      stripe_half_length_fraction = [
        [settings.fetch('stripe_half_length_fraction', 0.45).to_f, 0.20].max,
        0.49
      ].min
      stripe_spacing_fraction = [
        [settings.fetch('stripe_spacing_fraction', 0.13).to_f, 0.04].max,
        0.25
      ].min
      surface_offset_m = [
        [settings.fetch('surface_offset_m', 0.002).to_f, 0.0005].max,
        0.02
      ].min
      stripe_half_width = bounds.width.to_f * stripe_half_width_fraction
      stripe_half_length = bounds.height.to_f * stripe_half_length_fraction
      z = bounds.min.z + surface_offset_m.m
      stripe_thickness = [bounds.depth.to_f, 0.02.m.to_f].max
      center_index = (stripe_count - 1) / 2.0
      marking_group = definition.entities.add_group
      marking_group.name = 'PT_CROSSWALK_MARKINGS'
      marking_group.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'generated_detail',
        'crosswalk_markings'
      )
      stripe_count.times do |index|
        center_x = bounds.center.x + (index - center_index) * bounds.width.to_f * stripe_spacing_fraction
        points = [
          Geom::Point3d.new(center_x - stripe_half_width, bounds.center.y - stripe_half_length, z),
          Geom::Point3d.new(center_x + stripe_half_width, bounds.center.y - stripe_half_length, z),
          Geom::Point3d.new(center_x + stripe_half_width, bounds.center.y + stripe_half_length, z),
          Geom::Point3d.new(center_x - stripe_half_width, bounds.center.y + stripe_half_length, z)
        ]
        face = marking_group.entities.add_face(points)
        next unless face

        face.reverse! if face.normal.z < 0
        face.pushpull(stripe_thickness)
      end
      marking_group.entities.grep(Sketchup::Face).each do |face|
        face.material = marking
        face.back_material = marking
      end
      marking_group.entities.grep(Sketchup::Edge).each { |edge| edge.hidden = true }
    end

    def apply_component_palette(
      entities,
      asset_id,
      model,
      root_bounds,
      transform = Geom::Transformation.new,
      visited = {}
    )
      root_height = [root_bounds.depth.to_f, 0.001].max
      entities.each do |entity|
        if entity.is_a?(Sketchup::Face)
          world_center = entity.bounds.center.transform(transform)
          ratio = (world_center.z - root_bounds.min.z) / root_height
          material = component_palette_material(model, asset_id, ratio)
          if material
            entity.material = material
            entity.back_material = material
          end
          # The bundled road-crossing asset is used only as a lightweight,
          # audited sizing frame.  Its original road tile and imported stripe
          # mesh are hidden so the generated, knowledge-driven white markings
          # remain clean and never fight with the host road surface.
          entity.hidden = true if asset_id == 'road_crossing'
        elsif entity.is_a?(Sketchup::Group) || entity.is_a?(Sketchup::ComponentInstance)
          if asset_id == 'road_crossing'
            entity.hidden = true
            next
          end
          definition = entity.definition
          next if visited[definition.object_id]

          visited[definition.object_id] = true
          apply_component_palette(
            definition.entities,
            asset_id,
            model,
            root_bounds,
            transform * entity.transformation,
            visited
          )
        elsif entity.is_a?(Sketchup::Edge)
          if asset_id == 'road_crossing'
            entity.hidden = true
          elsif %w[tree_large tree_small street_light parasol].include?(asset_id) &&
                entity.faces.length == 2
            entity.soft = true
            entity.smooth = true
          end
        end
      end
    end

    def bundled_component_definition(model, asset, counts)
      return nil unless asset.is_a?(Hash)

      file_name = asset['skp_file'].to_s
      asset_id = asset['asset_id'].to_s
      return nil if file_name.empty? || asset_id.empty?
      return nil unless File.basename(file_name) == file_name && File.extname(file_name).downcase == '.skp'

      cached = model.definitions.find do |definition|
        definition.get_attribute(ATTRIBUTE_DICTIONARY, 'component_asset_id') == asset_id
      end
      return cached if cached

      user_path = File.join(USER_COMPONENT_DIR, file_name)
      if asset['native_generator'] && !File.file?(user_path)
        return native_component_definition(model, asset, counts)
      end
      path = File.file?(user_path) ? user_path : File.join(COMPONENT_DIR, file_name)
      return nil unless File.file?(path)

      definition = model.definitions.load(path)
      return nil unless definition

      user_override = path == user_path
      definition.name = "PT_LIBRARY_#{asset_id.upcase}"
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_asset_id', asset_id)
      definition.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_source_id',
        user_override ? 'user-provided' : asset['source_id']
      )
      definition.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_license',
        user_override ? 'USER-PROVIDED' : asset['license']
      )
      definition.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_origin',
        user_override ? 'user_override' : 'bundled'
      )
      if asset_id == 'road_crossing' && !user_override
        source_bounds = definition.bounds
        definition.entities.erase_entities(definition.entities.to_a)
        add_road_crossing_markings(
          definition,
          model,
          asset.fetch('facility_rendering', {}),
          source_bounds
        )
      else
        apply_component_palette(definition.entities, asset_id, model, definition.bounds)
      end
      counts[:library_definitions_loaded] += 1
      definition
    rescue StandardError
      nil
    end

    def add_bundled_component_instance(
      model,
      entities,
      asset,
      anchor,
      x_axis,
      y_axis,
      z_axis,
      counts,
      name:,
      layer_name:,
      anchor_mode: 'center_xy_base',
      scale_factor: 1.0
    )
      definition = bundled_component_definition(model, asset, counts)
      return nil unless definition

      target = asset.fetch('target_bounds_m', []).map(&:to_f)
      return nil unless target.length == 3 && target.all?(&:positive?)

      bounds = definition.bounds
      # SketchUp::Geom::BoundingBox exposes X/Y/Z as width/height/depth.
      # Keep that order aligned with target_bounds_m = [width, depth, height].
      # Swapping height and depth stretches upright components vertically and
      # turns flat road components into long ribbons.
      source = [bounds.width, bounds.height, bounds.depth].map do |length|
        length.to_f / (1.m).to_f
      end
      return nil unless source.all?(&:positive?)

      local_anchor = if anchor_mode == 'center_x_front_base'
                       Geom::Point3d.new(bounds.center.x, bounds.min.y, bounds.min.z)
                     else
                       Geom::Point3d.new(bounds.center.x, bounds.center.y, bounds.min.z)
                     end
      fit = Geom::Transformation.scaling(
        target[0] / source[0] * scale_factor,
        target[1] / source[1] * scale_factor,
        target[2] / source[2] * scale_factor
      )
      local_to_origin = Geom::Transformation.translation(
        Geom::Vector3d.new(-local_anchor.x, -local_anchor.y, -local_anchor.z)
      )
      axes = Geom::Transformation.axes(anchor, x_axis, y_axis, z_axis)
      instance = entities.add_instance(definition, axes * fit * local_to_origin)
      instance.name = name
      instance.layer = model.layers[layer_name] || model.layers.add(layer_name)
      instance.set_attribute(ATTRIBUTE_DICTIONARY, 'component_asset_id', asset['asset_id'])
      instance.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_source_id',
        definition.get_attribute(ATTRIBUTE_DICTIONARY, 'component_source_id')
      )
      instance.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_license',
        definition.get_attribute(ATTRIBUTE_DICTIONARY, 'component_license')
      )
      instance.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_origin',
        definition.get_attribute(ATTRIBUTE_DICTIONARY, 'component_origin')
      )
      counts[:library_components] += 1
      instance
    rescue StandardError
      nil
    end

    def attach_metadata(entity, object)
      entity.set_attribute(ATTRIBUTE_DICTIONARY, 'object_id', object['id'])
      entity.set_attribute(ATTRIBUTE_DICTIONARY, 'parent_id', object['parent_id'])
      entity.set_attribute(ATTRIBUTE_DICTIONARY, 'source_handle', object['source_handle'])
      entity.set_attribute(ATTRIBUTE_DICTIONARY, 'source_layer', object['source_layer'])
      entity.set_attribute(ATTRIBUTE_DICTIONARY, 'source_type', object['source_type'])
      entity.set_attribute(ATTRIBUTE_DICTIONARY, 'role', object['role'])
      entity.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'geometry_fingerprint',
        object['geometry_fingerprint']
      ) if object['geometry_fingerprint']
      entity.set_attribute(ATTRIBUTE_DICTIONARY, 'block_name', object['block_name']) if object['block_name']
      if object['surface_generation_suppressed']
        entity.set_attribute(
          ATTRIBUTE_DICTIONARY,
          'surface_generation_suppressed',
          true
        )
        entity.set_attribute(
          ATTRIBUTE_DICTIONARY,
          'surface_suppression_reason',
          object['surface_suppression_reason']
        )
      end
    end

    def add_coloured_face(entities, points, material, counts, count_key = :detail_faces)
      face = entities.add_face(points)
      return nil unless face

      face.material = material
      face.back_material = material
      counts[count_key] += 1
      face
    end

    def add_floor_guides(entities, base_points, settings, counts)
      elevations = settings.fetch('floor_line_elevations_m', [])
      return if elevations.empty?

      base_z = base_points.map(&:z).min
      elevations.each do |elevation_m|
        level_points = base_points.map do |point|
          Geom::Point3d.new(point.x, point.y, base_z + elevation_m.to_f.m)
        end
        level_points.each_with_index do |point, index|
          entities.add_line(point, level_points[(index + 1) % level_points.length])
          counts[:floor_guides] += 1
        end
      end
    end

    def midpoint_at_height(first, second, z_value)
      Geom::Point3d.new(
        (first.x + second.x) / 2.0,
        (first.y + second.y) / 2.0,
        z_value
      )
    end

    def add_flat_parapet(entities, top_points, height_m, model, counts)
      return unless height_m.positive?

      material = roof_material(model)
      top_points.each_with_index do |point, index|
        next_point = top_points[(index + 1) % top_points.length]
        raised_next = Geom::Point3d.new(next_point.x, next_point.y, next_point.z + height_m.m)
        raised_point = Geom::Point3d.new(point.x, point.y, point.z + height_m.m)
        add_coloured_face(
          entities,
          [point, next_point, raised_next, raised_point],
          material,
          counts,
          :parapet_faces
        )
      end
    end

    def add_gable_roof(entities, top_points, roof_height_m, model, counts)
      return false unless top_points.length == 4 && roof_height_m.positive?

      lengths = top_points.each_with_index.map do |point, index|
        point.distance(top_points[(index + 1) % 4])
      end
      material = roof_material(model)
      ridge_z = top_points.map(&:z).max + roof_height_m.m
      if lengths[0] + lengths[2] >= lengths[1] + lengths[3]
        ridge_a = midpoint_at_height(top_points[3], top_points[0], ridge_z)
        ridge_b = midpoint_at_height(top_points[1], top_points[2], ridge_z)
        faces = [
          [top_points[0], top_points[1], ridge_b, ridge_a],
          [top_points[2], top_points[3], ridge_a, ridge_b],
          [top_points[1], top_points[2], ridge_b],
          [top_points[3], top_points[0], ridge_a]
        ]
      else
        ridge_a = midpoint_at_height(top_points[0], top_points[1], ridge_z)
        ridge_b = midpoint_at_height(top_points[2], top_points[3], ridge_z)
        faces = [
          [top_points[1], top_points[2], ridge_b, ridge_a],
          [top_points[3], top_points[0], ridge_a, ridge_b],
          [top_points[0], top_points[1], ridge_a],
          [top_points[2], top_points[3], ridge_b]
        ]
      end
      faces.each { |points| add_coloured_face(entities, points, material, counts, :roof_faces) }
      true
    end

    def add_hip_roof(entities, top_points, roof_height_m, model, counts)
      return false unless top_points.length == 4 && roof_height_m.positive?

      centre = Geom::Point3d.new(
        top_points.map(&:x).sum / top_points.length,
        top_points.map(&:y).sum / top_points.length,
        top_points.map(&:z).max + roof_height_m.m
      )
      material = roof_material(model)
      top_points.each_with_index do |point, index|
        add_coloured_face(
          entities,
          [point, top_points[(index + 1) % top_points.length], centre],
          material,
          counts,
          :roof_faces
        )
      end
      true
    end

    def window_definition(model, facade)
      width_m = facade.fetch('window_width_m', 1.6).to_f
      height_m = facade.fetch('window_height_m', 1.5).to_f
      depth_m = facade.fetch('depth_m', 0.06).to_f
      signature = [width_m, height_m, depth_m].map { |value| format('%.2f', value) }.join('_')
      name = "PT_WINDOW_#{signature}"
      definition = model.definitions[name] || model.definitions.add(name)
      # Sketchup::Entities is collection-like but does not implement Ruby's
      # Enumerable#empty? in SketchUp 2026.  Use its native length API so an
      # existing shared window definition can be reused across versions.
      return definition if definition.entities.length.positive?

      points = [
        Geom::Point3d.new((-width_m / 2.0).m, 0, 0),
        Geom::Point3d.new((width_m / 2.0).m, 0, 0),
        Geom::Point3d.new((width_m / 2.0).m, 0, height_m.m),
        Geom::Point3d.new((-width_m / 2.0).m, 0, height_m.m)
      ]
      face = definition.entities.add_face(points)
      if face
        face.material = window_material(model)
        face.back_material = window_material(model)
        face.pushpull(depth_m.m) if depth_m.positive?
      end
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_role', 'facade_window')
      definition
    end

    def signed_area_xy(points)
      points.each_with_index.sum do |point, index|
        next_point = points[(index + 1) % points.length]
        point.x * next_point.y - next_point.x * point.y
      end / 2.0
    end

    def longest_facade(base_points)
      ccw = signed_area_xy(base_points).positive?
      z_axis = Geom::Vector3d.new(0, 0, 1)
      candidates = base_points.each_with_index.map do |point, index|
        next_point = base_points[(index + 1) % base_points.length]
        [point.distance(next_point), index, point, next_point]
      end
      length, index, point, next_point = candidates.max_by(&:first)
      edge_axis = point.vector_to(next_point)
      edge_axis.normalize!
      outward = ccw ? edge_axis.cross(z_axis) : z_axis.cross(edge_axis)
      outward.normalize!
      facade_axis = ccw ? edge_axis.reverse : edge_axis
      midpoint = Geom::Point3d.new(
        (point.x + next_point.x) / 2.0,
        (point.y + next_point.y) / 2.0,
        [point.z, next_point.z].min
      )
      {
        index: index,
        length: length,
        x_axis: facade_axis,
        outward: outward,
        midpoint: midpoint,
        z_axis: z_axis
      }
    end

    def door_definition(model, settings)
      width_m = settings.fetch('width_m', 2.4).to_f
      height_m = settings.fetch('height_m', 2.4).to_f
      signature = [width_m, height_m].map { |value| format('%.2f', value) }.join('_')
      name = "PT_ENTRANCE_#{signature}"
      definition = model.definitions[name] || model.definitions.add(name)
      return definition if definition.entities.length.positive?

      frame_points = [
        Geom::Point3d.new((-width_m / 2.0).m, 0, 0),
        Geom::Point3d.new((width_m / 2.0).m, 0, 0),
        Geom::Point3d.new((width_m / 2.0).m, 0, height_m.m),
        Geom::Point3d.new((-width_m / 2.0).m, 0, height_m.m)
      ]
      frame = definition.entities.add_face(frame_points)
      if frame
        frame.material = detail_material(model, 'door_frame')
        frame.back_material = detail_material(model, 'door_frame')
      end
      glass_points = [
        Geom::Point3d.new((-width_m * 0.40).m, 0.015.m, 0.14.m),
        Geom::Point3d.new((width_m * 0.40).m, 0.015.m, 0.14.m),
        Geom::Point3d.new((width_m * 0.40).m, 0.015.m, (height_m - 0.14).m),
        Geom::Point3d.new((-width_m * 0.40).m, 0.015.m, (height_m - 0.14).m)
      ]
      glass = definition.entities.add_face(glass_points)
      if glass
        glass.material = detail_material(model, 'door_glass')
        glass.back_material = detail_material(model, 'door_glass')
      end
      definition.entities.add_line(
        Geom::Point3d.new(0, 0.02.m, 0.14.m),
        Geom::Point3d.new(0, 0.02.m, (height_m - 0.14).m)
      )
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_role', 'building_entrance')
      definition
    end

    def canopy_definition(model, settings)
      width_m = settings.fetch('canopy_width_m', 3.0).to_f
      depth_m = settings.fetch('canopy_depth_m', 1.0).to_f
      thickness_m = settings.fetch('canopy_thickness_m', 0.18).to_f
      signature = [width_m, depth_m, thickness_m].map { |value| format('%.2f', value) }.join('_')
      name = "PT_CANOPY_#{signature}"
      definition = model.definitions[name] || model.definitions.add(name)
      return definition if definition.entities.length.positive?

      face = definition.entities.add_face(
        Geom::Point3d.new((-width_m / 2.0).m, 0, 0),
        Geom::Point3d.new((width_m / 2.0).m, 0, 0),
        Geom::Point3d.new((width_m / 2.0).m, depth_m.m, 0),
        Geom::Point3d.new((-width_m / 2.0).m, depth_m.m, 0)
      )
      if face
        face.material = detail_material(model, 'metal')
        face.back_material = detail_material(model, 'metal')
        face.pushpull(thickness_m.m)
      end
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_role', 'entrance_canopy')
      definition
    end

    def balcony_definition(model, settings)
      width_m = settings.fetch('width_m', 3.6).to_f
      depth_m = settings.fetch('depth_m', 1.25).to_f
      thickness_m = settings.fetch('slab_thickness_m', 0.16).to_f
      rail_m = settings.fetch('railing_height_m', 1.05).to_f
      signature = [width_m, depth_m, thickness_m, rail_m].map { |value| format('%.2f', value) }.join('_')
      name = "PT_BALCONY_#{signature}"
      definition = model.definitions[name] || model.definitions.add(name)
      return definition if definition.entities.length.positive?

      slab = definition.entities.add_face(
        Geom::Point3d.new((-width_m / 2.0).m, 0, 0),
        Geom::Point3d.new((width_m / 2.0).m, 0, 0),
        Geom::Point3d.new((width_m / 2.0).m, depth_m.m, 0),
        Geom::Point3d.new((-width_m / 2.0).m, depth_m.m, 0)
      )
      if slab
        slab.material = detail_material(model, 'metal')
        slab.back_material = detail_material(model, 'metal')
        slab.pushpull(-thickness_m.m)
      end
      rail_points = [
        Geom::Point3d.new((-width_m / 2.0).m, depth_m.m, 0),
        Geom::Point3d.new((-width_m / 2.0).m, depth_m.m, rail_m.m),
        Geom::Point3d.new((width_m / 2.0).m, depth_m.m, rail_m.m),
        Geom::Point3d.new((width_m / 2.0).m, depth_m.m, 0)
      ]
      definition.entities.add_edges(rail_points)
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_role', 'residential_balcony')
      definition
    end

    def rooftop_definition(model, settings)
      height_m = settings.fetch('height_m', 1.2).to_f
      name = "PT_ROOFTOP_EQUIPMENT_#{format('%.2f', height_m)}"
      definition = model.definitions[name] || model.definitions.add(name)
      return definition if definition.entities.length.positive?

      face = definition.entities.add_face(
        Geom::Point3d.new(-1.2.m, -0.9.m, 0),
        Geom::Point3d.new(1.2.m, -0.9.m, 0),
        Geom::Point3d.new(1.2.m, 0.9.m, 0),
        Geom::Point3d.new(-1.2.m, 0.9.m, 0)
      )
      if face
        face.material = detail_material(model, 'equipment')
        face.back_material = detail_material(model, 'equipment')
        face.pushpull(height_m.m)
      end
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_role', 'rooftop_equipment')
      definition
    end

    def add_plinth_panels(entities, base_points, settings, model, counts)
      return unless settings['enabled']

      height_m = settings.fetch('height_m', 0.45).to_f
      offset_m = settings.fetch('offset_m', 0.04).to_f
      ccw = signed_area_xy(base_points).positive?
      z_axis = Geom::Vector3d.new(0, 0, 1)
      base_points.each_with_index do |point, index|
        next_point = base_points[(index + 1) % base_points.length]
        edge_axis = point.vector_to(next_point)
        next unless edge_axis.valid?

        edge_axis.normalize!
        outward = ccw ? edge_axis.cross(z_axis) : z_axis.cross(edge_axis)
        outward.normalize!
        lower_a = point.offset(outward, offset_m.m)
        lower_b = next_point.offset(outward, offset_m.m)
        upper_a = Geom::Point3d.new(lower_a.x, lower_a.y, lower_a.z + height_m.m)
        upper_b = Geom::Point3d.new(lower_b.x, lower_b.y, lower_b.z + height_m.m)
        add_coloured_face(
          entities,
          [lower_a, lower_b, upper_b, upper_a],
          detail_material(model, 'plinth'),
          counts,
          :plinth_faces
        )
      end
    end

    def add_architectural_details(model, entities, base_points, settings, height_m, counts)
      details = settings.fetch('architectural_details', {})
      return unless details['enabled']

      add_plinth_panels(entities, base_points, details.fetch('plinth', {}), model, counts)
      facade = longest_facade(base_points)
      entrance = details.fetch('entrance', {})
      if entrance['enabled']
        origin = facade[:midpoint].offset(facade[:outward], 0.04.m)
        transform = Geom::Transformation.axes(
          origin,
          facade[:x_axis],
          facade[:outward],
          facade[:z_axis]
        )
        door = entities.add_instance(door_definition(model, entrance), transform)
        door.name = 'PT_ENTRANCE'
        door.layer = model.layers['PT_DETAIL'] || model.layers.add('PT_DETAIL')
        canopy_origin = Geom::Point3d.new(
          origin.x,
          origin.y,
          origin.z + entrance.fetch('height_m', 2.4).to_f.m + 0.18.m
        )
        canopy = add_bundled_component_instance(
          model,
          entities,
          entrance['component_library'],
          canopy_origin,
          facade[:x_axis],
          facade[:outward],
          facade[:z_axis],
          counts,
          name: 'PT_ENTRANCE_CANOPY',
          layer_name: 'PT_DETAIL',
          anchor_mode: 'center_x_front_base'
        )
        unless canopy
          canopy_transform = Geom::Transformation.axes(
            canopy_origin,
            facade[:x_axis],
            facade[:outward],
            facade[:z_axis]
          )
          canopy = entities.add_instance(canopy_definition(model, entrance), canopy_transform)
        end
        canopy.name = 'PT_ENTRANCE_CANOPY'
        canopy.layer = model.layers['PT_DETAIL'] || model.layers.add('PT_DETAIL')
        counts[:entrances] += 1
        counts[:entrance_canopies] += 1
        counts[:library_entrance_canopies] += 1 if canopy.get_attribute(
          ATTRIBUTE_DICTIONARY,
          'component_asset_id'
        )
      end

      balcony = details.fetch('balcony', {})
      if balcony['enabled']
        floor_height_m = settings.fetch('floor_height_m', 3.0).to_f
        floor_count = settings.fetch('floor_count', 0).to_i
        max_instances = balcony.fetch('max_instances', 8).to_i
        levels = (1...floor_count).to_a.first(max_instances)
        levels.each do |level|
          origin = facade[:midpoint].offset(facade[:outward], 0.06.m)
          origin = Geom::Point3d.new(
            origin.x,
            origin.y,
            origin.z + (level * floor_height_m).m
          )
          transform = Geom::Transformation.axes(
            origin,
            facade[:x_axis],
            facade[:outward],
            facade[:z_axis]
          )
          instance = entities.add_instance(balcony_definition(model, balcony), transform)
          instance.name = 'PT_BALCONY'
          instance.layer = model.layers['PT_DETAIL'] || model.layers.add('PT_DETAIL')
          counts[:balconies] += 1
        end
      end

      rooftop = details.fetch('rooftop_equipment', {})
      if rooftop['enabled']
        centre = Geom::Point3d.new(
          base_points.map(&:x).sum / base_points.length,
          base_points.map(&:y).sum / base_points.length,
          base_points.map(&:z).max + height_m.m + 0.05.m
        )
        instance = entities.add_instance(
          rooftop_definition(model, rooftop),
          Geom::Transformation.translation(centre)
        )
        instance.name = 'PT_ROOFTOP_EQUIPMENT'
        instance.layer = model.layers['PT_DETAIL'] || model.layers.add('PT_DETAIL')
        counts[:rooftop_equipment] += 1
      end
    end

    def add_facade_components(entities, base_points, settings, model, counts)
      facade = settings.fetch('facade', {})
      return unless facade['enabled']

      floors = settings.fetch('floor_count', 0).to_i
      floor_height_m = settings.fetch('floor_height_m', 0).to_f
      return unless floors.positive? && floor_height_m.positive?

      definition = window_definition(model, facade)
      module_width_m = facade.fetch('module_width_m', 3.6).to_f
      margin_m = facade.fetch('margin_m', 0.6).to_f
      sill_height_m = facade.fetch('sill_height_m', 0.9).to_f
      max_instances = facade.fetch('max_instances', 1500).to_i
      if counts.key?(:facade_per_building_limit)
        max_instances = [max_instances, counts[:facade_per_building_limit]].min
      end
      base_z = base_points.map(&:z).min
      ccw = signed_area_xy(base_points).positive?
      z_axis = Geom::Vector3d.new(0, 0, 1)
      candidates = []
      entrance = settings.dig('architectural_details', 'entrance') || {}
      entrance_edge = longest_facade(base_points)[:index]
      entrance_width_m = entrance.fetch('width_m', 0).to_f

      base_points.each_with_index do |point, edge_index|
        next_point = base_points[(edge_index + 1) % base_points.length]
        edge_length_m = point.distance(next_point).to_f / (1.m).to_f
        available_m = edge_length_m - margin_m * 2.0
        next unless available_m.positive?

        modules = [(available_m / module_width_m).floor, 1].max
        spacing_m = available_m / modules
        x_axis = point.vector_to(next_point)
        x_axis.normalize!
        y_axis = z_axis.cross(x_axis)
        y_axis.normalize!
        outward = ccw ? x_axis.cross(z_axis) : z_axis.cross(x_axis)
        outward.normalize!

        floors.times do |floor_index|
          modules.times do |module_index|
            distance_m = margin_m + spacing_m * (module_index + 0.5)
            if entrance['enabled'] && edge_index == entrance_edge && floor_index.zero?
              entrance_clearance = entrance_width_m / 2.0 + facade.fetch('window_width_m', 1.6).to_f / 2.0
              next if (distance_m - edge_length_m / 2.0).abs <= entrance_clearance
            end
            origin = point.offset(x_axis, distance_m.m)
            origin = Geom::Point3d.new(
              origin.x,
              origin.y,
              base_z + (floor_index * floor_height_m + sill_height_m).m
            )
            origin = origin.offset(outward, 0.02.m)
            candidates << [origin, x_axis.clone, y_axis.clone]
          end
        end
      end
      if candidates.length > max_instances
        candidates = Array.new(max_instances) do |index|
          candidates[(index * candidates.length.to_f / max_instances).floor]
        end
      end
      candidates.each do |origin, x_axis, y_axis|
        transform = Geom::Transformation.axes(origin, x_axis, y_axis, z_axis)
        instance = entities.add_instance(definition, transform)
        instance.name = 'PT_WINDOW'
        instance.layer = model.layers['PT_FACADE'] || model.layers.add('PT_FACADE')
        counts[:facade_components] += 1
      end
    end

    def add_procedural_details(model, building_group, object, base_points, counts)
      settings = object.fetch('procedural_modeling', {})
      return unless settings['enabled']

      details = building_group.entities.add_group
      details.name = 'PT_PROCEDURAL_DETAILS'
      details.layer = model.layers['PT_DETAIL'] || model.layers.add('PT_DETAIL')
      details.set_attribute(ATTRIBUTE_DICTIONARY, 'generated_detail', true)
      add_floor_guides(details.entities, base_points, settings, counts)

      height_m = object.fetch('extrusion_m', 0).to_f
      top_points = base_points.map do |point|
        Geom::Point3d.new(point.x, point.y, point.z + height_m.m)
      end
      roof_type = settings.fetch('effective_roof_type', 'flat')
      roof_height_m = settings.fetch('roof_height_m', 0).to_f
      if roof_type == 'gable'
        add_gable_roof(details.entities, top_points, roof_height_m, model, counts)
      elsif roof_type == 'hip'
        add_hip_roof(details.entities, top_points, roof_height_m, model, counts)
      else
        add_flat_parapet(
          details.entities,
          top_points,
          settings.fetch('parapet_height_m', 0).to_f,
          model,
          counts
        )
      end
      add_architectural_details(
        model,
        details.entities,
        base_points,
        settings,
        height_m,
        counts
      )
      add_facade_components(details.entities, base_points, settings, model, counts)
      counts[:procedural_buildings] += 1
    end

    def tree_ring(radius_m, elevation_m, segments)
      Array.new(segments) do |index|
        angle = 2.0 * Math::PI * index / segments
        Geom::Point3d.new(
          (Math.cos(angle) * radius_m).m,
          (Math.sin(angle) * radius_m).m,
          elevation_m.m
        )
      end
    end

    def add_tree_canopy(entities, settings, material)
      radius_m = settings.fetch('canopy_radius_m', 2.0).to_f
      trunk_height_m = settings.fetch('trunk_height_m', 2.8).to_f
      canopy_height_m = settings.fetch('canopy_height_m', 3.6).to_f
      segments = [[settings.fetch('segments', 8).to_i, 6].max, 16].min
      tiers = settings.fetch('canopy_tiers', 1).to_i
      profiles = if tiers > 2
                   [[0.00, 0.38], [0.15, 0.78], [0.34, 1.00], [0.58, 0.92], [0.80, 0.62], [1.00, 0.12]]
                 elsif tiers > 1
                   [[0.00, 0.42], [0.22, 0.88], [0.45, 1.00], [0.74, 0.62], [1.00, 0.12]]
                 else
                   [[0.00, 0.50], [0.42, 1.00], [1.00, 0.12]]
                 end
      base_z_m = trunk_height_m * 0.72
      rings = profiles.map do |height_ratio, radius_ratio|
        tree_ring(
          radius_m * radius_ratio,
          base_z_m + canopy_height_m * height_ratio,
          segments
        )
      end
      rings.each_cons(2) do |lower, upper|
        segments.times do |index|
          face = entities.add_face(
            lower[index],
            lower[(index + 1) % segments],
            upper[(index + 1) % segments],
            upper[index]
          )
          next unless face

          face.material = material
          face.back_material = material
        end
      end
      [rings.first.reverse, rings.last].each do |ring|
        face = entities.add_face(ring)
        next unless face

        face.material = material
        face.back_material = material
      end
    end

    def tree_definition(model, settings)
      values = %w[canopy_radius_m trunk_radius_m trunk_height_m canopy_height_m].map do |key|
        format('%.2f', settings.fetch(key, 0).to_f)
      end
      signature = ([settings.fetch('segments', 8), settings.fetch('canopy_tiers', 1)] + values).join('_')
      name = "PT_TREE_#{signature}"
      definition = model.definitions[name] || model.definitions.add(name)
      return definition if definition.entities.length.positive?

      trunk_radius_m = settings.fetch('trunk_radius_m', 0.2).to_f
      trunk_height_m = settings.fetch('trunk_height_m', 2.8).to_f
      segments = [[settings.fetch('segments', 8).to_i, 6].max, 16].min
      trunk_points = tree_ring(trunk_radius_m, 0.0, segments)
      trunk_face = definition.entities.add_face(trunk_points)
      if trunk_face
        trunk_face.material = tree_trunk_material(model)
        trunk_face.back_material = tree_trunk_material(model)
        trunk_face.pushpull(trunk_height_m.m)
      end
      add_tree_canopy(definition.entities, settings, tree_canopy_material(model))
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'component_role', 'site_tree')
      definition.set_attribute(ATTRIBUTE_DICTIONARY, 'detail_level', settings['detail_level'])
      definition
    end

    def add_tree_component(model, entities, object, counts)
      settings = object.fetch('procedural_symbol', {})
      return nil unless settings['enabled'] && settings['type'] == 'tree'

      centre = points_from_metres([settings.fetch('center_m')]).first
      rotation = settings.fetch('rotation_deg', 0).to_f.degrees
      scale = settings.fetch('scale_factor', 1.0).to_f
      x_axis = Geom::Vector3d.new(Math.cos(rotation), Math.sin(rotation), 0)
      y_axis = Geom::Vector3d.new(-Math.sin(rotation), Math.cos(rotation), 0)
      instance = add_bundled_component_instance(
        model,
        entities,
        settings['component_library'],
        centre,
        x_axis,
        y_axis,
        Z_AXIS,
        counts,
        name: 'PT_TREE',
        layer_name: 'PT_GREEN',
        scale_factor: scale
      )
      unless instance
        transform = (
          Geom::Transformation.translation(centre) *
          Geom::Transformation.rotation(ORIGIN, Z_AXIS, rotation) *
          Geom::Transformation.scaling(scale)
        )
        instance = entities.add_instance(tree_definition(model, settings), transform)
      end
      instance.name = 'PT_TREE'
      instance.layer = model.layers['PT_GREEN'] || model.layers.add('PT_GREEN')
      counts[:tree_components] += 1
      counts[:library_tree_components] += 1 if instance.get_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_asset_id'
      )
      counts[:varied_tree_components] += 1 if rotation.nonzero? || (scale - 1.0).abs > 0.001
      instance
    end

    def add_explicit_library_component(model, entities, object, counts)
      settings = object.fetch('procedural_symbol', {})
      return nil unless settings['enabled'] && settings['type'] == 'library_component'

      centre = points_from_metres([settings.fetch('center_m')]).first
      rotation = settings.fetch('rotation_deg', 0).to_f.degrees
      x_axis = Geom::Vector3d.new(Math.cos(rotation), Math.sin(rotation), 0)
      y_axis = Geom::Vector3d.new(-Math.sin(rotation), Math.cos(rotation), 0)
      instance = add_bundled_component_instance(
        model,
        entities,
        settings['component_library'],
        centre,
        x_axis,
        y_axis,
        Z_AXIS,
        counts,
        name: "PT_#{settings.dig('component_library', 'asset_id').to_s.upcase}",
        layer_name: object.fetch('sketchup_tag', 'PT_DETAIL')
      )
      counts[:explicit_library_components] += 1 if instance
      if instance
        asset_id = settings.dig('component_library', 'asset_id').to_s
        counts[:traffic_lights] += 1 if asset_id == 'traffic_light'
        if asset_id == 'road_crossing'
          counts[:road_crossing_components] += 1
          %w[
            cad_rotation_deg rotation_deg orientation_mode orientation_source
            matched_road_id matched_road_axis_deg orientation_confidence
            orientation_rule matched_road_geometry matched_road_local_frame_index
            road_width_source
          ].each do |key|
            value = settings[key]
            instance.set_attribute(ATTRIBUTE_DICTIONARY, key, value) unless value.nil?
          end
        end
      end
      instance
    end

    def add_procedural_symbol_component(model, entities, object, counts)
      type = object.dig('procedural_symbol', 'type')
      return add_tree_component(model, entities, object, counts) if type == 'tree'
      return add_explicit_library_component(model, entities, object, counts) if type == 'library_component'

      nil
    end

    # Derive a stable local frame for ordered, near-rectangular road polygons.
    # Curved/segmented roads use the separate local-tangent path below; all
    # other irregular polygons keep the original lightweight CAD slab.
    def road_frame(points, style)
      settings = style.fetch('road_design', {})
      return nil unless settings['enabled'] && points.length == 4

      edges = points.each_with_index.map do |point, index|
        next_point = points[(index + 1) % points.length]
        [point.distance(next_point), point, next_point, index]
      end
      longest = edges.max_by(&:first)
      length, first, second, long_index = longest
      opposite = edges[(long_index + 2) % 4]
      width_a = edges[(long_index + 1) % 4][0]
      width_b = edges[(long_index + 3) % 4][0]
      return nil unless length.positive? && opposite[0].positive? && width_a.positive? && width_b.positive?

      long_ratio = [length, opposite[0]].min / [length, opposite[0]].max
      width_ratio = [width_a, width_b].min / [width_a, width_b].max
      return nil if long_ratio < 0.82 || width_ratio < 0.72

      points.each_with_index do |point, index|
        previous = points[(index - 1) % points.length]
        following = points[(index + 1) % points.length]
        first_axis = point.vector_to(previous)
        second_axis = point.vector_to(following)
        next unless first_axis.valid? && second_axis.valid?

        first_axis.normalize!
        second_axis.normalize!
        return nil if (first_axis % second_axis).abs > 0.24
      end

      axis = first.vector_to(second)
      axis.normalize!
      normal = Z_AXIS.cross(axis)
      normal.normalize!
      long_midpoint = Geom.linear_combination(0.5, first, 0.5, second)
      opposite_midpoint = Geom.linear_combination(0.5, opposite[1], 0.5, opposite[2])
      toward_opposite = long_midpoint.vector_to(opposite_midpoint)
      normal.reverse! if (normal % toward_opposite).negative?
      width = (normal % toward_opposite).abs
      length_m = ((length + opposite[0]) / 2.0).to_f / (1.m).to_f
      width_m = width.to_f / (1.m).to_f
      return nil if length_m < settings.fetch('minimum_length_m', 8.0).to_f
      return nil if width_m < settings.fetch('minimum_width_m', 4.0).to_f

      {
        center: Geom.linear_combination(0.5, long_midpoint, 0.5, opposite_midpoint),
        axis: axis,
        normal: normal,
        length_m: length_m,
        width_m: width_m,
        z: points.map(&:z).max
      }
    end

    def road_frame_point(frame, longitudinal_m, lateral_m, z_offset_m = 0.0)
      point = frame[:center]
              .offset(frame[:axis], longitudinal_m.m)
              .offset(frame[:normal], lateral_m.m)
      Geom::Point3d.new(point.x, point.y, frame[:z] + z_offset_m.m)
    end

    # Convert the Python-side local tangent hint into a bounded, editable
    # SketchUp path.  The hint is deliberately treated as untrusted input:
    # malformed, sparse, or implausibly narrow frames return an empty path so
    # the original CAD surface remains the only geometry that is shown.
    def curved_road_records(points, style)
      settings = style.fetch('road_design', {})
      return [] unless settings['enabled']

      hint = style.fetch('geometry_hint', {})
      return [] unless hint.is_a?(Hash) && hint['eligible']
      return [] unless %w[curved_strip segmented_strip centerline_corridor].include?(hint['shape'])

      raw_frames = hint['frames']
      return [] unless raw_frames.is_a?(Array) && raw_frames.length.between?(2, 64)

      z = points.map(&:z).max
      previous_axis = nil
      records = []
      raw_frames.each_with_index do |raw, index|
        next unless raw.is_a?(Hash)

        center = raw['center_m']
        axis_values = raw['axis_vector']
        width_m = raw['width_m'].to_f
        next unless center.is_a?(Array) && center.length >= 2
        next unless axis_values.is_a?(Array) && axis_values.length >= 2
        next unless width_m >= settings.fetch('minimum_width_m', 4.0).to_f
        next unless center.first.is_a?(Numeric) && center[1].is_a?(Numeric)

        axis = Geom::Vector3d.new(
          axis_values[0].to_f,
          axis_values[1].to_f,
          0
        )
        next unless axis.valid? && axis.length > 1e-6

        axis.normalize!
        if previous_axis && (previous_axis % axis).negative?
          axis.reverse!
        end
        previous_axis = axis.clone
        normal = Geom::Vector3d.new(-axis.y, axis.x, 0)
        normal.normalize!
        records << {
          index: index,
          center: Geom::Point3d.new(center[0].to_f.m, center[1].to_f.m, z),
          axis: axis,
          normal: normal,
          width_m: width_m,
          z: z,
          hint_station_m: raw['station_m'].is_a?(Numeric) ? raw['station_m'].to_f : nil
        }
      end
      return [] if records.length < 2

      total_m = 0.0
      records.each_cons(2) do |first, second|
        total_m += first[:center].distance(second[:center]).to_f / (1.m).to_f
      end
      return [] if total_m < settings.fetch('minimum_length_m', 8.0).to_f

      station_m = 0.0
      records.each_with_index do |record, index|
        if index.positive?
          previous = records[index - 1]
          station_m += previous[:center].distance(record[:center]).to_f / (1.m).to_f
        end
        record[:station_m] = station_m
        record[:longitudinal_m] = station_m - total_m / 2.0
      end
      records
    end

    def curved_road_point(record, lateral_m, z_offset_m = 0.0)
      point = record[:center].offset(record[:normal], lateral_m.to_f.m)
      Geom::Point3d.new(point.x, point.y, record[:z] + z_offset_m.to_f.m)
    end

    def curved_road_sample(records, distance_m)
      return nil if records.length < 2

      total_m = records.last[:station_m].to_f
      target_m = [[distance_m.to_f, 0.0].max, total_m].min
      segment_index = records.length - 2
      (records.length - 1).times do |index|
        if target_m <= records[index + 1][:station_m].to_f
          segment_index = index
          break
        end
      end
      first = records[segment_index]
      second = records[segment_index + 1]
      segment_start = first[:station_m].to_f
      segment_length = second[:station_m].to_f - segment_start
      ratio = segment_length.positive? ? (target_m - segment_start) / segment_length : 0.0
      ratio = [[ratio, 0.0].max, 1.0].min
      center = Geom::Point3d.new(
        first[:center].x + (second[:center].x - first[:center].x) * ratio,
        first[:center].y + (second[:center].y - first[:center].y) * ratio,
        first[:z] + (second[:z] - first[:z]) * ratio
      )
      axis = first[:center].vector_to(second[:center])
      axis = first[:axis].clone unless axis.valid? && axis.length > 1e-6
      axis.normalize!
      normal = Geom::Vector3d.new(-axis.y, axis.x, 0)
      normal.normalize!
      hint_longitudinal_m = if first[:hint_station_m].is_a?(Numeric) && second[:hint_station_m].is_a?(Numeric)
                              first[:hint_station_m].to_f +
                                (second[:hint_station_m].to_f - first[:hint_station_m].to_f) * ratio
                            else
                              target_m - total_m / 2.0
                            end
      {
        center: center,
        axis: axis,
        normal: normal,
        width_m: first[:width_m].to_f + (second[:width_m].to_f - first[:width_m].to_f) * ratio,
        z: center.z,
        longitudinal_m: target_m - total_m / 2.0,
        hint_longitudinal_m: hint_longitudinal_m
      }
    end

    def add_curved_band(
      entities,
      records,
      lateral_centers,
      widths_m,
      z_offset_m,
      material,
      counts,
      count_key = :road_curved_detail_faces
    )
      return 0 unless records.length >= 2
      return 0 unless lateral_centers.length == records.length
      return 0 unless widths_m.length == records.length

      created = 0
      records.each_cons(2).with_index do |(first, second), index|
        first_width = widths_m[index].to_f
        second_width = widths_m[index + 1].to_f
        next unless first_width.positive? && second_width.positive?

        first_half = first_width / 2.0
        second_half = second_width / 2.0
        points = [
          curved_road_point(first, lateral_centers[index].to_f - first_half, z_offset_m),
          curved_road_point(second, lateral_centers[index + 1].to_f - second_half, z_offset_m),
          curved_road_point(second, lateral_centers[index + 1].to_f + second_half, z_offset_m),
          curved_road_point(first, lateral_centers[index].to_f + first_half, z_offset_m)
        ]
        face = add_coloured_face(entities, points, material, counts, count_key)
        next unless face

        face.edges.each { |edge| edge.hidden = true }
        created += 1
      end
      created
    end

    def add_curved_road_dash(entities, records, start_m, finish_m, width_m, z_offset_m, material, counts)
      first = curved_road_sample(records, start_m)
      second = curved_road_sample(records, finish_m)
      return nil unless first && second && finish_m > start_m

      half_width = width_m.to_f / 2.0
      first_center = Geom::Point3d.new(first[:center].x, first[:center].y, first[:z] + z_offset_m.to_f.m)
      second_center = Geom::Point3d.new(second[:center].x, second[:center].y, second[:z] + z_offset_m.to_f.m)
      face = add_coloured_face(
        entities,
        [
          first_center.offset(first[:normal], -half_width.m),
          second_center.offset(second[:normal], -half_width.m),
          second_center.offset(second[:normal], half_width.m),
          first_center.offset(first[:normal], half_width.m)
        ],
        material,
        counts,
        :lane_markings
      )
      face.edges.each { |edge| edge.hidden = true } if face
      face
    end

    def add_curved_road_details(entities, points, style, model, counts)
      records = curved_road_records(points, style)
      return if records.length < 2

      settings = style.fetch('road_design', {})
      total_m = records.last[:station_m].to_f
      return if total_m < settings.fetch('minimum_length_m', 8.0).to_f

      counts[:road_curved_surfaces] += 1
      sidewalk = settings.fetch('sidewalk', {})
      sidewalk_widths = records.map do |record|
        road_cross_section({ width_m: record[:width_m] }, settings)[:sidewalk_width_m].to_f
      end
      sidewalk_width_m = sidewalk_widths.min.to_f
      if sidewalk['enabled'] && sidewalk_width_m.positive?
        lateral = records.map { |record| record[:width_m] / 2.0 - sidewalk_width_m / 2.0 }
        max_bands = [
          settings.fetch('geometry_budget', {}).fetch('max_sidewalk_bands', 2).to_i,
          2
        ].min
        [-1, 1].first(max_bands).each do |side|
          centers = lateral.map { |value| value * side }
          created = add_curved_band(
            entities,
            records,
            centers,
            Array.new(records.length, sidewalk_width_m),
            sidewalk.fetch('height_m', 0.12).to_f,
            detail_material(model, 'sidewalk'),
            counts
          )
          counts[:road_curved_sidewalk_faces] += created
          counts[:road_curved_sidewalk_bands] += 1 if created.positive?
        end
      end

      carriageway_widths = records.map do |record|
        record[:width_m] - (sidewalk_width_m * 2.0)
      end
      if carriageway_widths.min.to_f >= 5.5
        counts[:road_curved_two_way_surfaces] += 1
      end

      if style.dig('geometry_hint', 'shape') == 'centerline_corridor'
        created = add_curved_band(
          entities,
          records,
          Array.new(records.length, 0.0),
          carriageway_widths,
          0.0,
          material_for(model, 'road'),
          counts,
          :road_centerline_corridor_faces
        )
        counts[:road_centerline_corridor_surfaces] += 1 if created.positive?
      end

      edge = settings.fetch('edge_marking', {})
      if edge['enabled']
        line_width_m = edge.fetch('width_m', 0.12).to_f
        inset_m = edge.fetch('inset_m', 0.22).to_f
        2.times do |side_index|
          centers = records.each_with_index.map do |record, index|
            carriageway_half = carriageway_widths[index] / 2.0
            side = side_index.zero? ? -1.0 : 1.0
            side * (carriageway_half - inset_m - line_width_m / 2.0)
          end
          next unless centers.all?(&:finite?) && centers.zip(carriageway_widths).all? { |center, width| center.abs < width / 2.0 }

          created = add_curved_band(
            entities,
            records,
            centers,
            Array.new(records.length, line_width_m),
            0.021,
            detail_material(model, 'marking'),
            counts,
            :road_curved_edge_faces
          )
          counts[:road_curved_edge_lines] += 1 if created.positive?
        end
      end

      marking = style.fetch('lane_marking', {})
      if marking['enabled'] && carriageway_widths.min.to_f >= marking.fetch('minimum_road_width_m', 5.5).to_f
        dash_m = marking.fetch('dash_length_m', 3.0).to_f
        gap_m = marking.fetch('gap_length_m', 3.0).to_f
        margin_m = marking.fetch('margin_m', 2.0).to_f
        available_m = total_m - margin_m * 2.0
        if dash_m.positive? && gap_m >= 0 && available_m >= dash_m
          period_m = dash_m + gap_m
          dash_count = [((available_m + gap_m) / period_m).floor, 1].max
          dash_count = [dash_count, marking.fetch('max_dashes', 80).to_i].min
          first_center = -((dash_count - 1) * period_m) / 2.0
          dash_count.times do |index|
            center_m = total_m / 2.0 + first_center + index * period_m
            sample = curved_road_sample(records, center_m)
            next unless sample
            if road_detail_excluded?(sample[:hint_longitudinal_m], settings, dash_m / 2.0)
              counts[:road_lane_markings_avoided] += 1
              next
            end
            add_curved_road_dash(
              entities,
              records,
              center_m - dash_m / 2.0,
              center_m + dash_m / 2.0,
              marking.fetch('width_m', 0.12).to_f,
              0.021,
              detail_material(model, 'marking'),
              counts
            )
          end
        end
      end

      arrow = settings.fetch('direction_arrow', {})
      return unless arrow['enabled']
      return if carriageway_widths.min.to_f < arrow.fetch('minimum_road_width_m', 6.0).to_f
      return if total_m < arrow.fetch('minimum_road_length_m', 20.0).to_f

      max_total = [
        arrow.fetch('max_per_surface', 6).to_i,
        settings.fetch('geometry_budget', {}).fetch('max_arrows', 6).to_i
      ].min
      per_lane_budget = max_total / 2
      return unless per_lane_budget.positive?

      margin_m = arrow.fetch('end_margin_m', 8.0).to_f
      available_m = total_m - margin_m * 2.0
      return unless available_m.positive?

      per_lane = [(available_m / arrow.fetch('spacing_m', 30.0).to_f).floor + 1, 1].max
      per_lane = [per_lane, per_lane_budget].min
      positions = if per_lane == 1
                    [0.0]
                  else
                    Array.new(per_lane) do |index|
                      -total_m / 2.0 + margin_m + available_m * (index + 1) / (per_lane + 1).to_f
                    end
                  end
      lane_offset_m = [carriageway_widths.min.to_f * 0.25, 0.75].max
      maximum_offset_m = carriageway_widths.min.to_f / 2.0 - 0.45
      lane_offset_m = [lane_offset_m, maximum_offset_m].min
      return unless lane_offset_m.positive?

      positions.each do |longitudinal_m|
        sample = curved_road_sample(records, total_m / 2.0 + longitudinal_m)
        next unless sample

        [[-lane_offset_m, sample[:axis]], [lane_offset_m, Geom::Vector3d.new(-sample[:axis].x, -sample[:axis].y, -sample[:axis].z)]].each do |lateral_m, direction|
          if road_detail_excluded?(sample[:hint_longitudinal_m], settings, arrow.fetch('length_m', 2.7).to_f / 2.0)
            counts[:road_direction_arrows_avoided] += 1
            next
          end
          center = sample[:center].offset(sample[:normal], lateral_m.m)
          add_road_direction_arrow(
            entities,
            sample,
            center,
            direction,
            arrow.fetch('length_m', 2.7).to_f,
            [arrow.fetch('width_m', 0.9).to_f, carriageway_widths.min.to_f * 0.32].min,
            model,
            counts
          )
        end
      end
    end

    # Build a true ring from an explicitly named ROUNDABOUT/环岛 curve.  The
    # source CIRCLE remains an editable reference edge; its interior is not
    # filled as a solid disk.  Width and sampling are accepted only from the
    # audited Python hint, so an arbitrary circle never becomes a road by
    # accident.
    def roundabout_road_records(points, style)
      settings = style.fetch('road_design', {})
      return [] unless settings['enabled']

      hint = style.fetch('geometry_hint', {})
      return [] unless hint.is_a?(Hash) && hint['eligible']
      return [] unless hint['shape'] == 'roundabout_ring'

      center_values = hint['center_m']
      radius_m = hint['centerline_radius_m'].to_f
      width_m = hint['width_m'].to_f
      raw_frames = hint['frames']
      return [] unless center_values.is_a?(Array) && center_values.length >= 2
      return [] unless raw_frames.is_a?(Array) && raw_frames.length.between?(12, 64)
      return [] unless radius_m.positive? && width_m >= settings.fetch('minimum_width_m', 4.0).to_f
      return [] unless center_values.first.is_a?(Numeric) && center_values[1].is_a?(Numeric)

      center = Geom::Point3d.new(center_values[0].to_f.m, center_values[1].to_f.m, points.map(&:z).max)
      records = raw_frames.each_with_index.filter_map do |raw, index|
        next unless raw.is_a?(Hash)

        frame_center = raw['center_m']
        axis_values = raw['axis_vector']
        next unless frame_center.is_a?(Array) && frame_center.length >= 2
        next unless axis_values.is_a?(Array) && axis_values.length >= 2

        radial = center.vector_to(
          Geom::Point3d.new(frame_center[0].to_f.m, frame_center[1].to_f.m, center.z)
        )
        next unless radial.valid? && radial.length > 1e-6

        radial.normalize!
        axis = Geom::Vector3d.new(axis_values[0].to_f, axis_values[1].to_f, 0)
        next unless axis.valid? && axis.length > 1e-6

        axis.normalize!
        {
          index: index,
          center: Geom::Point3d.new(frame_center[0].to_f.m, frame_center[1].to_f.m, center.z),
          radial: radial,
          axis: axis,
          radius_m: radius_m,
          width_m: width_m,
          z: center.z,
          hint_station_m: raw['station_m'].is_a?(Numeric) ? raw['station_m'].to_f : nil
        }
      end
      records.length >= 12 ? records : []
    end

    def roundabout_road_point(record, radial_offset_m, z_offset_m = 0.0)
      point = record[:center].offset(record[:radial], radial_offset_m.to_f.m)
      Geom::Point3d.new(point.x, point.y, record[:z] + z_offset_m.to_f.m)
    end

    def add_roundabout_band(entities, records, radial_offset_m, width_m, z_offset_m, material, counts, count_key)
      return 0 unless records.length >= 12 && width_m.to_f.positive?

      created = 0
      records.each_with_index do |first, index|
        second = records[(index + 1) % records.length]
        half_width = width_m.to_f / 2.0
        points = [
          roundabout_road_point(first, radial_offset_m.to_f - half_width, z_offset_m),
          roundabout_road_point(second, radial_offset_m.to_f - half_width, z_offset_m),
          roundabout_road_point(second, radial_offset_m.to_f + half_width, z_offset_m),
          roundabout_road_point(first, radial_offset_m.to_f + half_width, z_offset_m)
        ]
        face = add_coloured_face(entities, points, material, counts, count_key)
        next unless face

        face.reverse! if face.normal.z < 0
        face.edges.each { |edge| edge.hidden = true }
        created += 1
      end
      created
    end

    def add_roundabout_road_details(entities, points, style, model, counts)
      records = roundabout_road_records(points, style)
      return if records.length < 12

      settings = style.fetch('road_design', {})
      width_m = records.map { |record| record[:width_m].to_f }.min
      return unless width_m >= settings.fetch('minimum_width_m', 4.0).to_f

      counts[:road_roundabout_surfaces] += 1
      add_roundabout_band(
        entities,
        records,
        0.0,
        width_m,
        0.0,
        material_for(model, 'road'),
        counts,
        :road_roundabout_detail_faces
      )

      sidewalk_width_m = road_cross_section({ width_m: width_m }, settings)[:sidewalk_width_m].to_f
      sidewalk = settings.fetch('sidewalk', {})
      if sidewalk['enabled'] && sidewalk_width_m.positive?
        [-1.0, 1.0].each do |side|
          add_roundabout_band(
            entities,
            records,
            side * (width_m / 2.0 + sidewalk_width_m / 2.0),
            sidewalk_width_m,
            sidewalk.fetch('height_m', 0.12).to_f,
            detail_material(model, 'sidewalk'),
            counts,
            :road_roundabout_sidewalk_faces
          )
          counts[:road_roundabout_sidewalk_bands] += 1
        end
      end

      edge = settings.fetch('edge_marking', {})
      if edge['enabled']
        line_width_m = edge.fetch('width_m', 0.12).to_f
        inset_m = edge.fetch('inset_m', 0.22).to_f
        [-1.0, 1.0].each do |side|
          boundary = side * (width_m / 2.0 - inset_m - line_width_m / 2.0)
          next unless boundary.abs < width_m / 2.0

          created = add_roundabout_band(
            entities,
            records,
            boundary,
            line_width_m,
            0.021,
            detail_material(model, 'marking'),
            counts,
            :road_roundabout_edge_faces
          )
          counts[:road_roundabout_edge_lines] += 1 if created.positive?
        end
      end

      # A circulating carriageway does not receive straight-road arrows or a
      # center dashed line.  Keep the decision explicit for later reports.
      counts[:road_roundabout_center_marking_suppressed] += 1
    end

    def add_road_band(
      entities,
      frame,
      lateral_center_m,
      width_m,
      end_margin_m,
      z_offset_m,
      material,
      counts,
      count_key,
      vertical_sides = false
    )
      half_length_m = frame[:length_m] / 2.0 - end_margin_m
      half_width_m = width_m / 2.0
      return nil unless half_length_m > 0.1 && half_width_m.positive?

      points = [
        road_frame_point(frame, -half_length_m, lateral_center_m - half_width_m, z_offset_m),
        road_frame_point(frame, half_length_m, lateral_center_m - half_width_m, z_offset_m),
        road_frame_point(frame, half_length_m, lateral_center_m + half_width_m, z_offset_m),
        road_frame_point(frame, -half_length_m, lateral_center_m + half_width_m, z_offset_m)
      ]
      face = entities.add_face(points)
      return nil unless face

      face.reverse! if face.normal.z < 0
      face.material = material
      face.back_material = material
      if vertical_sides && z_offset_m.positive?
        base_points = [
          road_frame_point(frame, -half_length_m, lateral_center_m - half_width_m, 0.004),
          road_frame_point(frame, half_length_m, lateral_center_m - half_width_m, 0.004),
          road_frame_point(frame, half_length_m, lateral_center_m + half_width_m, 0.004),
          road_frame_point(frame, -half_length_m, lateral_center_m + half_width_m, 0.004)
        ]
        4.times do |index|
          side_face = entities.add_face(
            base_points[index],
            base_points[(index + 1) % 4],
            points[(index + 1) % 4],
            points[index]
          )
          next unless side_face

          side_face.material = material
          side_face.back_material = material
          counts[:road_sidewalk_side_faces] += 1
        end
      end
      counts[count_key] += 1
      face
    end

    def road_cross_section(frame, settings)
      sidewalk = settings.fetch('sidewalk', {})
      sidewalk_width_m = 0.0
      if sidewalk['enabled'] &&
         frame[:width_m] >= sidewalk.fetch('minimum_total_road_width_m', 8.0).to_f
        preferred_m = sidewalk.fetch('preferred_width_m', 1.5).to_f
        maximum_m = frame[:width_m] * sidewalk.fetch('maximum_fraction_each_side', 0.22).to_f
        sidewalk_width_m = [preferred_m, maximum_m].min
        minimum_carriageway_m = sidewalk.fetch('minimum_carriageway_width_m', 5.5).to_f
        if frame[:width_m] - sidewalk_width_m * 2.0 < minimum_carriageway_m
          sidewalk_width_m = (frame[:width_m] - minimum_carriageway_m) / 2.0
        end
        minimum_sidewalk_m = sidewalk.fetch('minimum_width_m', 1.0).to_f
        sidewalk_width_m = 0.0 if sidewalk_width_m < minimum_sidewalk_m
      end
      {
        sidewalk_width_m: sidewalk_width_m,
        carriageway_width_m: frame[:width_m] - sidewalk_width_m * 2.0
      }
    end

    def road_detail_excluded?(longitudinal_m, settings, half_length_m = 0.0)
      zones = settings.fetch('exclusion_zones', [])
      return false unless zones.is_a?(Array)

      zones.any? do |zone|
        next false unless zone.is_a?(Hash)

        center_m = zone.fetch('center_longitudinal_m', 0.0).to_f
        clearance_m = zone.fetch('half_length_m', 0.0).to_f
        (longitudinal_m.to_f - center_m).abs <= clearance_m + half_length_m.to_f
      end
    end

    def add_road_direction_arrow(
      entities,
      frame,
      center,
      direction,
      length_m,
      width_m,
      model,
      counts
    )
      direction = direction.clone
      direction.normalize!
      side = Z_AXIS.cross(direction)
      side.normalize!
      half_length = length_m.m / 2.0
      shaft_end = length_m.m * 0.08
      half_shaft = width_m.m * 0.18
      half_head = width_m.m / 2.0
      z = frame[:z] + 0.022.m
      point = lambda do |longitudinal, lateral|
        raw = center.offset(direction, longitudinal).offset(side, lateral)
        Geom::Point3d.new(raw.x, raw.y, z)
      end
      polygon = [
        point.call(-half_length, -half_shaft),
        point.call(shaft_end, -half_shaft),
        point.call(shaft_end, -half_head),
        point.call(half_length, 0),
        point.call(shaft_end, half_head),
        point.call(shaft_end, half_shaft),
        point.call(-half_length, half_shaft)
      ]
      face = entities.add_face(polygon)
      return nil unless face

      face.reverse! if face.normal.z < 0
      face.material = detail_material(model, 'marking')
      face.back_material = detail_material(model, 'marking')
      counts[:road_direction_arrows] += 1
      face
    end

    def add_road_cross_section(entities, points, style, model, counts)
      settings = style.fetch('road_design', {})
      frame = road_frame(points, style)
      return unless frame

      section = road_cross_section(frame, settings)
      sidewalk_width_m = section[:sidewalk_width_m]
      carriageway_width_m = section[:carriageway_width_m]
      counts[:road_design_surfaces] += 1
      counts[:road_two_way_surfaces] += 1 if carriageway_width_m >= 5.5

      sidewalk = settings.fetch('sidewalk', {})
      if sidewalk_width_m.positive?
        budget = settings.fetch('geometry_budget', {})
        max_bands = [budget.fetch('max_sidewalk_bands', 2).to_i, 2].min
        lateral = frame[:width_m] / 2.0 - sidewalk_width_m / 2.0
        [-lateral, lateral].first(max_bands).each do |offset_m|
          add_road_band(
            entities,
            frame,
            offset_m,
            sidewalk_width_m,
            sidewalk.fetch('end_margin_m', 0.45).to_f,
            sidewalk.fetch('height_m', 0.12).to_f,
            detail_material(model, 'sidewalk'),
            counts,
            :road_sidewalk_bands,
            true
          )
        end
      end

      edge = settings.fetch('edge_marking', {})
      if edge['enabled']
        budget = settings.fetch('geometry_budget', {})
        max_lines = [budget.fetch('max_edge_lines', 2).to_i, 2].min
        line_width_m = edge.fetch('width_m', 0.12).to_f
        inset_m = edge.fetch('inset_m', 0.22).to_f
        carriageway_half_m = carriageway_width_m / 2.0
        lateral = carriageway_half_m - inset_m - line_width_m / 2.0
        if lateral.positive?
          [-lateral, lateral].first(max_lines).each do |offset_m|
            add_road_band(
              entities,
              frame,
              offset_m,
              line_width_m,
              style.dig('lane_marking', 'margin_m').to_f,
              0.021,
              detail_material(model, 'marking'),
              counts,
              :road_edge_lines
            )
          end
        end
      end

      arrow = settings.fetch('direction_arrow', {})
      return unless arrow['enabled']
      return if frame[:width_m] < arrow.fetch('minimum_road_width_m', 6.0).to_f
      return if frame[:length_m] < arrow.fetch('minimum_road_length_m', 20.0).to_f

      margin_m = arrow.fetch('end_margin_m', 8.0).to_f
      available_m = frame[:length_m] - margin_m * 2.0
      return unless available_m.positive?

      max_total = [
        arrow.fetch('max_per_surface', 6).to_i,
        settings.fetch('geometry_budget', {}).fetch('max_arrows', 6).to_i
      ].min
      per_lane_budget = max_total / 2
      return unless per_lane_budget.positive?

      spacing_m = arrow.fetch('spacing_m', 30.0).to_f
      per_lane = [(available_m / spacing_m).floor + 1, 1].max
      per_lane = [per_lane, per_lane_budget].min
      positions = if per_lane == 1
                    [0.0]
                  else
                    Array.new(per_lane) do |index|
                      -frame[:length_m] / 2.0 + margin_m +
                        available_m * (index + 1) / (per_lane + 1).to_f
                    end
                  end
      lane_offset_m = [carriageway_width_m * 0.25, 0.75].max
      maximum_offset_m = carriageway_width_m / 2.0 - 0.45
      lane_offset_m = [lane_offset_m, maximum_offset_m].min
      return unless lane_offset_m.positive?

      reverse_axis = Geom::Vector3d.new(-frame[:axis].x, -frame[:axis].y, -frame[:axis].z)
      [[-lane_offset_m, frame[:axis]], [lane_offset_m, reverse_axis]].each do |lateral_m, direction|
        positions.each do |longitudinal_m|
          if road_detail_excluded?(
            longitudinal_m,
            settings,
            arrow.fetch('length_m', 2.7).to_f / 2.0
          )
            counts[:road_direction_arrows_avoided] += 1
            next
          end
          center = road_frame_point(frame, longitudinal_m, lateral_m, 0.0)
          add_road_direction_arrow(
            entities,
            frame,
            center,
            direction,
            arrow.fetch('length_m', 2.7).to_f,
            [arrow.fetch('width_m', 0.9).to_f, carriageway_width_m * 0.32].min,
            model,
            counts
          )
        end
      end
    end

    def add_surface_edge_details(entities, points, style, model, counts)
      profile = style.fetch('edge_profile', {})
      return unless profile['enabled'] && points.length >= 3

      treatment = profile.fetch('treatment', 'curb')
      width_m = profile.fetch('width_m', 0.15).to_f
      height_m = profile.fetch('height_m', 0.05).to_f
      material_key = {
        'curb' => 'curb',
        'marking' => 'marking',
        'bank' => 'bank',
        'edging' => 'edging'
      }.fetch(treatment, 'curb')
      material = detail_material(model, material_key)
      ccw = signed_area_xy(points).positive?
      z_axis = Geom::Vector3d.new(0, 0, 1)
      longest_edge = points.each_with_index.map do |point, index|
        point.distance(points[(index + 1) % points.length])
      end.max
      points.each_with_index do |point, index|
        next_point = points[(index + 1) % points.length]
        edge_length = point.distance(next_point)
        next unless edge_length.positive?
        if profile['skip_short_ends'] && points.length == 4 &&
           edge_length < longest_edge * 0.8
          next
        end

        edge_axis = point.vector_to(next_point)
        edge_axis.normalize!
        inward = ccw ? z_axis.cross(edge_axis) : edge_axis.cross(z_axis)
        inward.normalize!
        safe_width = [width_m.m, edge_length * 0.25].min
        inner_a = point.offset(inward, safe_width)
        inner_b = next_point.offset(inward, safe_width)
        lift = height_m.m
        outer_top_a = Geom::Point3d.new(point.x, point.y, point.z + lift)
        outer_top_b = Geom::Point3d.new(next_point.x, next_point.y, next_point.z + lift)
        inner_top_a = Geom::Point3d.new(inner_a.x, inner_a.y, inner_a.z + lift)
        inner_top_b = Geom::Point3d.new(inner_b.x, inner_b.y, inner_b.z + lift)
        add_coloured_face(
          entities,
          [outer_top_a, outer_top_b, inner_top_b, inner_top_a],
          material,
          counts,
          :site_edge_faces
        )
        unless treatment == 'marking'
          add_coloured_face(
            entities,
            [point, next_point, outer_top_b, outer_top_a],
            material,
            counts,
            :site_edge_faces
          )
        end
        counts[:site_edge_segments] += 1
        counts[:parking_markings] += 1 if treatment == 'marking'
        counts[:curb_segments] += 1 if treatment == 'curb'
      end
    end

    def add_road_lane_markings(entities, points, style, model, counts)
      marking = style.fetch('lane_marking', {})
      frame = road_frame(points, style)
      return unless marking['enabled'] && frame
      return if frame[:width_m] < marking.fetch('minimum_road_width_m', 5.5).to_f

      length_m = frame[:length_m]
      dash_m = marking.fetch('dash_length_m', 3.0).to_f
      gap_m = marking.fetch('gap_length_m', 3.0).to_f
      margin_m = marking.fetch('margin_m', 2.0).to_f
      available_m = length_m - margin_m * 2.0
      return unless available_m >= dash_m

      period_m = dash_m + gap_m
      dash_count = [((available_m + gap_m) / period_m).floor, 1].max
      dash_count = [dash_count, marking.fetch('max_dashes', 100).to_i].min
      axis = frame[:axis]
      normal = frame[:normal]
      centre = Geom::Point3d.new(
        frame[:center].x,
        frame[:center].y,
        frame[:z] + 0.018.m
      )
      first_offset_m = -((dash_count - 1) * period_m) / 2.0
      half_dash = (dash_m / 2.0).m
      half_width = (marking.fetch('width_m', 0.12).to_f / 2.0).m
      dash_count.times do |index|
        longitudinal_m = first_offset_m + index * period_m
        if road_detail_excluded?(
          longitudinal_m,
          style.fetch('road_design', {}),
          dash_m / 2.0
        )
          counts[:road_lane_markings_avoided] += 1
          next
        end
        dash_centre = centre.offset(axis, longitudinal_m.m)
        start = dash_centre.offset(axis, -half_dash)
        finish = dash_centre.offset(axis, half_dash)
        face = entities.add_face(
          start.offset(normal, -half_width),
          finish.offset(normal, -half_width),
          finish.offset(normal, half_width),
          start.offset(normal, half_width)
        )
        next unless face

        face.material = detail_material(model, 'marking')
        face.back_material = detail_material(model, 'marking')
        counts[:lane_markings] += 1
      end
    end

    # Place street lights along the same trusted local tangent frames used by
    # curved road surfaces.  A curved road must not fall back to a global
    # rectangle axis: doing so rotates the fixtures away from the carriageway
    # and makes the two sides drift into the crosswalk.
    def add_curved_road_street_lights(entities, points, style, model, counts)
      settings = style.fetch('street_lights', {})
      return unless settings['enabled']

      records = curved_road_records(points, style)
      return if records.length < 2

      total_m = records.last[:station_m].to_f
      minimum_m = settings.fetch('minimum_edge_length_m', 24.0).to_f
      spacing_m = settings.fetch('spacing_m', 18.0).to_f
      margin_m = settings.fetch('end_margin_m', 6.0).to_f
      max_instances = settings.fetch('max_instances', 12).to_i
      return if total_m < minimum_m || spacing_m <= 0 || max_instances <= 0

      available_m = total_m - margin_m * 2.0
      return unless available_m.positive?

      count = [(available_m / spacing_m).floor + 1, 1].max
      count = [count, (max_instances / 2.0).ceil].min
      positions = if count == 1
                    [total_m / 2.0]
                  else
                    Array.new(count) do |index|
                      margin_m + available_m * index / (count - 1).to_f
                    end
                  end
      z_axis = Geom::Vector3d.new(0, 0, 1)
      placed = 0
      positions.each do |station_m|
        sample = curved_road_sample(records, station_m)
        next unless sample

        [-1.0, 1.0].each do |side|
          break if placed >= max_instances

          longitudinal_m = sample[:hint_longitudinal_m]
          if road_detail_excluded?(longitudinal_m, style.fetch('road_design', {}), 0.5)
            counts[:road_street_lights_avoided] += 1
            next
          end

          edge_offset_m = [sample[:width_m].to_f / 2.0 - 0.7, 0.1].max
          anchor_direction = sample[:normal].clone
          anchor_direction.reverse! if side.negative?
          anchor = sample[:center].offset(anchor_direction, edge_offset_m.m)
          anchor = Geom::Point3d.new(anchor.x, anchor.y, sample[:z] + 0.04.m)
          inward = sample[:normal].clone
          inward.reverse! if side.positive?
          instance = add_bundled_component_instance(
            model,
            entities,
            settings['component_library'],
            anchor,
            sample[:axis],
            inward,
            z_axis,
            counts,
            name: 'PT_STREET_LIGHT',
            layer_name: 'PT_DETAIL'
          )
          next unless instance

          instance.set_attribute(ATTRIBUTE_DICTIONARY, 'road_geometry', 'curved_local_tangent')
          instance.set_attribute(
            ATTRIBUTE_DICTIONARY,
            'road_local_station_m',
            sample[:hint_longitudinal_m]
          )
          instance.set_attribute(
            ATTRIBUTE_DICTIONARY,
            'road_local_axis_deg',
            (Math.atan2(sample[:axis].y, sample[:axis].x) * 180.0 / Math::PI) % 180.0
          )
          instance.set_attribute(ATTRIBUTE_DICTIONARY, 'road_side', side)
          counts[:street_lights] += 1
          counts[:road_curved_street_lights] += 1
          placed += 1
        end
      end
    end

    def add_road_street_lights(entities, points, style, model, counts)
      settings = style.fetch('street_lights', {})
      return unless settings['enabled']
      if points.length != 4
        add_curved_road_street_lights(entities, points, style, model, counts)
        return
      end
      frame = road_frame(points, style)
      return unless frame

      minimum_m = settings.fetch('minimum_edge_length_m', 24.0).to_f
      spacing_m = settings.fetch('spacing_m', 18.0).to_f
      margin_m = settings.fetch('end_margin_m', 6.0).to_f
      max_instances = settings.fetch('max_instances', 12).to_i
      return unless spacing_m.positive? && max_instances.positive?

      edges = points.each_with_index.map do |point, index|
        next_point = points[(index + 1) % points.length]
        [point.distance(next_point).to_f / (1.m).to_f, point, next_point]
      end
      longest_m = edges.map(&:first).max.to_f
      selected = edges.select do |length_m, _first, _second|
        length_m >= minimum_m && length_m >= longest_m * 0.8
      end
      return if selected.empty?

      ccw = signed_area_xy(points).positive?
      z_axis = Geom::Vector3d.new(0, 0, 1)
      placed = 0
      selected.each do |length_m, first, second|
        break if placed >= max_instances

        available_m = length_m - margin_m * 2.0
        next unless available_m.positive?

        edge_axis = first.vector_to(second)
        edge_axis.normalize!
        inward = ccw ? z_axis.cross(edge_axis) : edge_axis.cross(z_axis)
        inward.normalize!
        count = [(available_m / spacing_m).floor + 1, 1].max
        count = [count, max_instances - placed].min
        count.times do |index|
          distance_m = if count == 1
                         length_m / 2.0
                       else
                         margin_m + available_m * index / (count - 1).to_f
                       end
          anchor = first.offset(edge_axis, distance_m.m).offset(inward, 0.7.m)
          anchor = Geom::Point3d.new(anchor.x, anchor.y, points.map(&:z).max + 0.04.m)
          delta = frame[:center].vector_to(anchor)
          longitudinal_m = (
            delta.x * frame[:axis].x +
            delta.y * frame[:axis].y +
            delta.z * frame[:axis].z
          ) / 1.m.to_f
          if road_detail_excluded?(
            longitudinal_m,
            style.fetch('road_design', {})
          )
            counts[:road_street_lights_avoided] += 1
            next
          end
          instance = add_bundled_component_instance(
            model,
            entities,
            settings['component_library'],
            anchor,
            edge_axis,
            inward,
            z_axis,
            counts,
            name: 'PT_STREET_LIGHT',
            layer_name: 'PT_DETAIL'
          )
          return unless instance

          counts[:street_lights] += 1
          placed += 1
        end
      end
    end

    def create_object(model, parent_entities, object, counts)
      group = parent_entities.add_group
      role = object.fetch('role', 'other')
      tag_name = object.fetch('sketchup_tag', 'PT_OTHER')
      group.layer = model.layers[tag_name] || model.layers.add(tag_name)
      suffix = object.fetch('id', 'UNKNOWN').split('-').last
      group.name = if object['geometry_type'] == 'group'
                     "PT_BLOCK_#{object.fetch('block_name', 'UNNAMED')}_#{suffix}"
                   elsif object['geometry_type'] == 'linework_bundle'
                     "PT_UNDERLAY_#{suffix}"
                   elsif object['geometry_type'] == 'image_underlay'
                     "PT_UNDERLAY_IMAGE_#{suffix}"
                   else
                     "#{tag_name}_#{suffix}"
                   end
      attach_metadata(group, object)

      if object['geometry_type'] == 'image_underlay'
        image_path = object.fetch('image_path')
        raise ArgumentError, "找不到锁定底图：#{image_path}" unless File.file?(image_path)

        expected_hash = object.fetch('image_sha256', '').to_s.downcase
        actual_hash = Digest::SHA256.file(image_path).hexdigest.downcase
        unless expected_hash.empty? || expected_hash == actual_hash
          raise ArgumentError, '锁定底图内容已改变，请从当前图片重新执行图转 CAD。'
        end
        origin = points_from_metres([object.fetch('origin_m')]).first
        width = object.fetch('width_m').to_f
        height = object.fetch('height_m').to_f
        raise ArgumentError, '锁定底图尺寸无效。' unless width.positive? && height.positive?

        image = group.entities.add_image(
          image_path,
          origin,
          width.m,
          height.m
        )
        attach_metadata(image, object) if image
        group.set_attribute(ATTRIBUTE_DICTIONARY, 'auto_lock', true)
        group.set_attribute(ATTRIBUTE_DICTIONARY, 'raster_underlay_count', 1)
        group.locked = true if object.fetch('locked_by_default', true)
        counts[:raster_underlays] += 1
        return group
      end

      if object['geometry_type'] == 'group' && object.dig('procedural_symbol', 'enabled')
        component = add_procedural_symbol_component(model, group.entities, object, counts)
        if component
          counts[:group] += 1
          return group
        end
      end

      if object['geometry_type'] == 'group'
        object.fetch('children', []).each do |child|
          create_object(model, group.entities, child, counts)
        end
        counts[:group] += 1
        return group
      end

      if object['geometry_type'] == 'text'
        point = points_from_metres([object.fetch('position_m')]).first
        text_entity = group.entities.add_text(object.fetch('text', ''), point)
        attach_metadata(text_entity, object) if text_entity
        counts[:text] += 1
        return group
      end

      if object['geometry_type'] == 'linework_bundle'
        source_paths = object.fetch('paths', [])
        edge_segment_count = 0
        source_paths.each do |path|
          path_points = points_from_metres(path.fetch('points_m', []))
          next if path_points.length < 2

          if path['closed'] && path_points.length >= 3 && path_points.first != path_points.last
            path_points = path_points + [path_points.first]
          end
          edges = group.entities.add_edges(path_points)
          edge_segment_count += edges.length if edges.respond_to?(:length)
        end
        group.set_attribute(ATTRIBUTE_DICTIONARY, 'auto_lock', true)
        group.set_attribute(
          ATTRIBUTE_DICTIONARY,
          'underlay_source_entity_count',
          source_paths.length
        )
        group.locked = true if object.fetch('locked_by_default', true)
        counts[:underlay_bundles] += 1
        counts[:underlay_source_entities] += source_paths.length
        counts[:underlay_edge_segments] += edge_segment_count
        counts[:edges] += source_paths.length
        return group
      end

      points = points_from_metres(object.fetch('points_m'))
      surface_style = object.fetch('surface_style', {})
      if surface_style['enabled']
        elevation = surface_style.fetch('elevation_m', 0).to_f.m
        points = points.map do |point|
          Geom::Point3d.new(point.x, point.y, point.z + elevation)
        end
      end
      if object['closed'] && object['surface_generation_suppressed']
        outline_points = points.first == points.last ? points : points + [points.first]
        group.entities.add_edges(outline_points)
        counts[:road_review_outlines] += 1
        counts[:edges] += 1
        return group
      end
      roundabout_hint = surface_style.dig('geometry_hint', 'shape') == 'roundabout_ring'
      if object['closed'] && roundabout_hint
        add_roundabout_road_details(group.entities, points, surface_style, model, counts)
        # Keep the source curve as a visible reference edge without filling
        # the central island into a solid disk.
        group.entities.add_edges(points)
        counts[:edges] += 1
        return group
      end
      centerline_corridor = surface_style.dig('geometry_hint', 'shape') == 'centerline_corridor'
      if !object['closed'] && centerline_corridor
        add_curved_road_details(group.entities, points, surface_style, model, counts)
        add_road_street_lights(group.entities, points, surface_style, model, counts)
        group.entities.add_edges(points)
        counts[:edges] += 1
        return group
      end
      if object['closed'] && points.length >= 3
        face = group.entities.add_face(points)
        if face
          face.reverse! if face.normal.z < 0
          material = if role == 'building'
                       building_type = object.dig('building_parameters', 'building_type') || 'generic'
                       knowledge_rgb = object.dig('procedural_modeling', 'material_rgb')
                       building_type_material(model, building_type, knowledge_rgb)
                     else
                       material_for(model, role)
                     end
          face.material = material
          face.back_material = material
          height_m = object.fetch('extrusion_m', 0).to_f
          face.pushpull(height_m.m) if height_m.positive?
          thickness_m = surface_style.fetch('thickness_m', 0).to_f
          if !height_m.positive? && thickness_m.positive?
            face.pushpull(-thickness_m.m)
            counts[:site_surface_slabs] += 1
          end
          counts[:styled_site_surfaces] += 1 if surface_style['enabled']
          add_surface_edge_details(group.entities, points, surface_style, model, counts)
          add_curved_road_details(group.entities, points, surface_style, model, counts)
          add_road_cross_section(group.entities, points, surface_style, model, counts)
          add_road_lane_markings(group.entities, points, surface_style, model, counts)
          add_road_street_lights(group.entities, points, surface_style, model, counts)
          add_procedural_details(model, group, object, points, counts) if height_m.positive?
          counts[:face] += 1
          return group
        end
      end
      group.entities.add_edges(points)
      counts[:edges] += 1
      group
    end

    def project_root(model, data, path, incremental)
      project = data.fetch('project', {})
      project_id = project['project_id']
      root = nil
      if incremental && project_id
        root = model.entities.grep(Sketchup::Group).find do |group|
          group.get_attribute(ATTRIBUTE_DICTIONARY, 'project_id') == project_id
        end
      end
      root ||= model.entities.add_group
      root.name = "Planning Toolbox - #{project.fetch('name', File.basename(path))}"
      root.set_attribute(ATTRIBUTE_DICTIONARY, 'project_id', project_id)
      root.set_attribute(ATTRIBUTE_DICTIONARY, 'crs', project.dig('crs', 'code'))
      root.set_attribute(ATTRIBUTE_DICTIONARY, 'handoff_path', path)
      root.set_attribute(ATTRIBUTE_DICTIONARY, 'source_sha256', data.dig('source', 'sha256'))
      root.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'modeling_knowledge_id',
        data.dig('modeling_settings', 'knowledge_base', 'id')
      )
      root.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'modeling_knowledge_version',
        data.dig('modeling_settings', 'knowledge_base', 'version')
      )
      root.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_library_id',
        data.dig('modeling_settings', 'component_library', 'id')
      )
      root.set_attribute(
        ATTRIBUTE_DICTIONARY,
        'component_library_version',
        data.dig('modeling_settings', 'component_library', 'version')
      )
      root
    end

    def existing_objects(root)
      root.entities.grep(Sketchup::Group).each_with_object({}) do |group, index|
        object_id = group.get_attribute(ATTRIBUTE_DICTIONARY, 'object_id')
        index[object_id] = group if object_id
      end
    end

    def import_object_incrementally(model, root, object, existing, incremental, counts)
      object_id = object['id']
      previous = incremental ? existing.delete(object_id) : nil
      if previous
        if previous.get_attribute(ATTRIBUTE_DICTIONARY, 'manual_lock', false)
          counts[:locked] += 1
          return previous
        end
        old_fingerprint = previous.get_attribute(ATTRIBUTE_DICTIONARY, 'geometry_fingerprint')
        new_fingerprint = object['geometry_fingerprint']
        if new_fingerprint && old_fingerprint == new_fingerprint
          counts[:unchanged] += 1
          return previous
        end
        if previous.get_attribute(ATTRIBUTE_DICTIONARY, 'auto_lock', false)
          previous.locked = false if previous.respond_to?(:locked=)
        end
        previous.erase! if previous.valid?
        counts[:updated] += 1
      else
        counts[:created] += 1
      end
      create_object(model, root.entities, object, counts)
    end

    def import_handoff_path(path, show_summary: true)
      raise ArgumentError, '没有提供 Planning Toolbox 交接文件路径。' if path.to_s.strip.empty?
      raise ArgumentError, "找不到 Planning Toolbox 交接文件：#{path}" unless File.file?(path)
      data = load_json(path)
      model = Sketchup.active_model
      counts = Hash.new(0)
      modeling = data.fetch('modeling_settings', {})
      incremental = modeling.fetch('incremental_update', false)
      facade_budget = modeling.fetch('facade_instance_budget', 0).to_i
      procedural_count = data.fetch('summary', {}).fetch('procedural_building_count', 0).to_i
      if facade_budget.positive? && procedural_count.positive?
        counts[:facade_per_building_limit] = [
          (facade_budget.to_f / procedural_count).ceil,
          4
        ].max
      end
      model.start_operation('导入 Planning Toolbox 模型交接', true)
      begin
        root = project_root(model, data, path, incremental)
        existing = incremental ? existing_objects(root) : {}
        data.fetch('objects').each_with_index do |object, index|
          import_object_incrementally(model, root, object, existing, incremental, counts)
          Sketchup.status_text = "Planning Toolbox 正在生成模型：#{index + 1}/#{data['objects'].length}"
        end
        counts[:orphaned] = existing.length
        model.commit_operation
        model.active_view.zoom_extents
      rescue StandardError
        model.abort_operation
        raise
      ensure
        Sketchup.status_text = ''
      end

      summary = (
        "模型交接完成。\n\n" \
        "新建：#{counts[:created]} 个\n更新：#{counts[:updated]} 个\n" \
        "未变化保留：#{counts[:unchanged]} 个\n手工锁定保护：#{counts[:locked]} 个\n" \
        "程序化建筑：#{counts[:procedural_buildings]} 个\n共享窗组件：#{counts[:facade_components]} 个\n" \
        "建筑入口：#{counts[:entrances]} 个\n入口雨棚：#{counts[:entrance_canopies]} 个\n" \
        "复用入口组件：#{counts[:library_entrance_canopies]} 个\n" \
        "住宅阳台：#{counts[:balconies]} 个\n屋顶设备：#{counts[:rooftop_equipment]} 个\n" \
        "共享树木组件：#{counts[:tree_components]} 个（组件库：#{counts[:library_tree_components]}）\n" \
        "显式场地组件：#{counts[:explicit_library_components]} 个\n" \
        "组件库总实例：#{counts[:library_components]} 个；加载定义：#{counts[:library_definitions_loaded]} 个\n" \
        "场地分层面：#{counts[:styled_site_surfaces]} 个\n街灯：#{counts[:street_lights]} 个\n" \
        "锁定参考底图：#{counts[:underlay_bundles]} 组（合并 #{counts[:underlay_source_entities]} 个源线对象）\n" \
        "锁定原始图片底图：#{counts[:raster_underlays]} 张\n" \
        "道路横断面：#{counts[:road_design_surfaces]} 条；人行道：#{counts[:road_sidewalk_bands]} 条\n" \
        "道路边线：#{counts[:road_edge_lines]} 条；方向箭头：#{counts[:road_direction_arrows]} 个\n" \
        "路缘/标线边段：#{counts[:site_edge_segments]} 条\n道路中心虚线：#{counts[:lane_markings]} 段\n" \
        "交通信号灯：#{counts[:traffic_lights]} 个；斑马线组件：#{counts[:road_crossing_components]} 个\n" \
        "屋顶面：#{counts[:roof_faces]} 个\n女儿墙面：#{counts[:parapet_faces]} 个\n" \
        "楼层辅助线：#{counts[:floor_guides]} 条\n保留的旧对象：#{counts[:orphaned]} 个\n\n" \
        '手工调整重点建筑前，可先在扩展程序菜单中锁定选中对象。'
      )
      UI.messagebox(summary) if show_summary
      counts
    rescue JSON::ParserError => error
      if show_summary
        UI.messagebox('交接文件不是有效 JSON，请回到 Planning Toolbox 重新导出。')
        nil
      else
        raise error
      end
    rescue StandardError => error
      if show_summary
        UI.messagebox("模型交接未完成：\n#{error.message}")
        nil
      else
        raise error
      end
    end

    def import_handoff
      path = UI.openpanel(
        '选择 Planning Toolbox SketchUp 交接文件',
        '',
        'Planning Toolbox 交接文件|*.ptsu.json||'
      )
      return unless path

      import_handoff_path(path, show_summary: true)
    end

    def set_selected_lock(value)
      model = Sketchup.active_model
      selected = model.selection.to_a.select do |entity|
        entity.respond_to?(:get_attribute) &&
          entity.get_attribute(ATTRIBUTE_DICTIONARY, 'object_id')
      end
      if selected.empty?
        UI.messagebox('请先选择一个由 Planning Toolbox 生成的建筑或对象分组。')
        return
      end

      model.start_operation(value ? '锁定 Planning Toolbox 对象' : '解除 Planning Toolbox 对象锁定', true)
      selected.each do |entity|
        entity.set_attribute(ATTRIBUTE_DICTIONARY, 'manual_lock', value)
      end
      model.commit_operation
      action = value ? '已锁定' : '已解除锁定'
      UI.messagebox("#{action} #{selected.length} 个对象。后续增量导入将#{value ? '保留' : '允许更新'}这些对象。")
    rescue StandardError => error
      model.abort_operation
      UI.messagebox("对象锁定操作未完成：\n#{error.message}")
    end

    def open_user_component_folder
      Dir.mkdir(File.dirname(USER_COMPONENT_DIR)) unless Dir.exist?(File.dirname(USER_COMPONENT_DIR))
      Dir.mkdir(USER_COMPONENT_DIR) unless Dir.exist?(USER_COMPONENT_DIR)
      guide = File.join(USER_COMPONENT_DIR, '使用说明.txt')
      unless File.file?(guide)
        File.write(
          guide,
          "Planning Toolbox 自定义 SketchUp 组件\n\n" \
          "把自己的轻量 SKP 复制到此文件夹，并使用以下文件名即可优先替换内置组件：\n" \
          "pt_tree_large.skp / pt_tree_small.skp / pt_street_light.skp\n" \
          "pt_awning_wide.skp / pt_overhang_wide.skp / pt_planter.skp / pt_parasol.skp\n" \
          "pt_road_crossing.skp / pt_traffic_light.skp\n\n" \
          "建议：单件小于 2 MB、原点位于底部、正面朝 +Y、不要携带无关场景和高分辨率纹理。\n" \
          "替换后新建 SketchUp 文件再导入；删除自定义文件即可恢复内置组件。\n"
        )
      end
      UI.openURL("file:///#{USER_COMPONENT_DIR.tr('\\', '/')}")
    rescue StandardError => error
      UI.messagebox("自定义组件文件夹未能打开：\n#{error.message}")
    end

    unless file_loaded?(__FILE__)
      menu = UI.menu('Extensions')
      import_command = UI::Command.new('导入 Planning Toolbox 模型交接...') { import_handoff }
      import_command.tooltip = '增量导入 .ptsu.json，并生成可编辑的规划建筑模型'
      menu.add_item(import_command)
      menu.add_separator
      menu.add_item('锁定选中的 Planning Toolbox 对象') { set_selected_lock(true) }
      menu.add_item('解除选中对象的锁定') { set_selected_lock(false) }
      menu.add_separator
      menu.add_item('打开 Planning Toolbox 自定义组件文件夹') { open_user_component_folder }
      file_loaded(__FILE__)
    end
  end
end

# Start the optional local MCP bridge after all handoff methods are defined.
require_relative 'mcp_bridge'
