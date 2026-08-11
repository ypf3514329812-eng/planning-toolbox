# frozen_string_literal: true

# Build small native SKP snapshots for the procedural component catalogue.
# The production extension uses native_generator; these files are compatibility
# snapshots for older plugin builds and for users who want to browse a part.
require 'json'
require 'fileutils'
require 'digest'

output_dir = ENV.fetch('PT_NATIVE_COMPONENT_OUTPUT_DIR')
report_path = ENV.fetch('PT_NATIVE_COMPONENT_REPORT')
FileUtils.mkdir_p(output_dir)

def pt_material(model, name, rgb, alpha = 1.0)
  material = model.materials[name] || model.materials.add(name)
  material.color = Sketchup::Color.new(*rgb)
  material.alpha = alpha
  material
end

def pt_paint(entities, before, material)
  (entities.grep(Sketchup::Face) - before).each do |face|
    face.material = material
    face.back_material = material
  end
end

def pt_box(entities, x, y, z, width, depth, height, material)
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
  pt_paint(entities, before, material)
end

def pt_cylinder(entities, x, y, z, radius, height, material, normal = Z_AXIS, segments = 10)
  before = entities.grep(Sketchup::Face)
  edges = entities.add_circle(Geom::Point3d.new(x.m, y.m, z.m), normal, radius.m, segments)
  face = entities.add_face(edges)
  return unless face

  face.pushpull(height.m)
  pt_paint(entities, before, material)
end

def pt_cone(entities, x, y, z, radius, height, material, top_ratio = 0.35, segments = 8)
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
  pt_paint(entities, before, material)
end

def build_component(model, generator)
  definition = model.definitions.add("PT_NATIVE_#{generator.upcase}")
  case generator
  when 'parked_car'
    body = pt_material(model, 'PT Vehicle Body', [87, 103, 111])
    trim = pt_material(model, 'PT Vehicle Trim', [48, 54, 57])
    glass = pt_material(model, 'PT Vehicle Glass', [105, 143, 153], 0.78)
    lamp = pt_material(model, 'PT Vehicle Lamp', [226, 188, 121])
    pt_box(definition.entities, -2.25, -0.82, 0.38, 4.5, 1.64, 0.55, body)
    pt_box(definition.entities, -1.15, -0.68, 0.93, 2.35, 1.36, 0.38, body)
    [[-0.97, -0.695], [0.10, -0.695], [-0.97, 1.0], [0.10, 1.0]].each do |x, y|
      pt_box(definition.entities, x, y, 1.0, 0.82, 0.025, 0.30, glass)
    end
    pt_box(definition.entities, -2.26, -0.58, 0.55, 0.08, 1.16, 0.18, lamp)
    pt_box(definition.entities, 2.18, -0.58, 0.55, 0.08, 1.16, 0.18, lamp)
    [-1.45, 1.45].each do |x|
      pt_cylinder(definition.entities, x, -0.92, 0.28, 0.34, 0.18, trim, Y_AXIS, 12)
      pt_cylinder(definition.entities, x, 0.74, 0.28, 0.34, 0.18, trim, Y_AXIS, 12)
    end
  when 'bench'
    wood = pt_material(model, 'PT Bench Wood', [157, 121, 83])
    metal = pt_material(model, 'PT Bench Metal', [83, 91, 91])
    3.times { |index| pt_box(definition.entities, -0.9, -0.30 + index * 0.20, 0.52, 1.8, 0.16, 0.10, wood) }
    2.times do |index|
      x = -0.72 + index * 1.44
      pt_box(definition.entities, x, -0.27, 0.0, 0.10, 0.54, 0.52, metal)
      pt_box(definition.entities, x, -0.25, 0.96, 0.10, 0.10, 0.72, metal)
    end
    3.times { |index| pt_box(definition.entities, -0.9, 0.22 + index * 0.18, 0.88, 1.8, 0.12, 0.10, wood) }
  when 'shrub_cluster'
    dark = pt_material(model, 'PT Shrub Dark', [86, 121, 82])
    light = pt_material(model, 'PT Shrub Light', [129, 157, 93])
    pt_cone(definition.entities, -0.62, 0.05, 0.0, 0.62, 1.15, dark, 0.42, 8)
    pt_cone(definition.entities, 0.15, -0.05, 0.0, 0.72, 1.35, light, 0.38, 8)
    pt_cone(definition.entities, 0.78, 0.18, 0.0, 0.48, 0.92, dark, 0.40, 8)
  when 'bollard'
    metal = pt_material(model, 'PT Bollard Metal', [76, 83, 83])
    band = pt_material(model, 'PT Bollard Band', [224, 190, 104])
    pt_cylinder(definition.entities, 0.0, 0.0, 0.0, 0.16, 0.10, metal, Z_AXIS, 10)
    pt_cylinder(definition.entities, 0.0, 0.0, 0.10, 0.09, 0.80, metal, Z_AXIS, 10)
    pt_cylinder(definition.entities, 0.0, 0.0, 0.58, 0.095, 0.10, band, Z_AXIS, 10)
    pt_cylinder(definition.entities, 0.0, 0.0, 0.90, 0.12, 0.10, metal, Z_AXIS, 10)
  when 'bus_shelter'
    metal = pt_material(model, 'PT Bus Shelter Metal', [77, 86, 87])
    glass = pt_material(model, 'PT Bus Shelter Glass', [136, 170, 178], 0.45)
    roof = pt_material(model, 'PT Bus Shelter Roof', [155, 139, 111])
    wood = pt_material(model, 'PT Bus Shelter Seat', [153, 119, 82])
    pt_box(definition.entities, -2.0, -0.8, 3.0, 4.0, 1.6, 0.16, roof)
    [-1.75, 1.60].each do |x|
      pt_box(definition.entities, x, -0.68, 0.0, 0.12, 0.12, 3.0, metal)
      pt_box(definition.entities, x, 0.56, 0.0, 0.12, 0.12, 3.0, metal)
    end
    pt_box(definition.entities, -1.60, 0.42, 0.0, 3.2, 0.05, 1.9, glass)
    pt_box(definition.entities, -1.50, -0.55, 0.52, 3.0, 0.55, 0.12, wood)
    pt_box(definition.entities, -1.30, -0.35, 0.64, 2.6, 0.08, 0.55, wood)
  else
    raise "unknown native generator: #{generator}"
  end
  definition
end

generators = {
  'parked_car' => 'pt_parked_car.skp',
  'bench' => 'pt_bench.skp',
  'shrub_cluster' => 'pt_shrub_cluster.skp',
  'bollard' => 'pt_bollard.skp',
  'bus_shelter' => 'pt_bus_shelter.skp'
}.freeze

UI.start_timer(2.5, false) do
  records = []
  begin
    generators.each do |generator, file_name|
      Sketchup.file_new
      model = Sketchup.active_model
      model.entities.erase_entities(model.entities.to_a)
      definition = build_component(model, generator)
      instance = model.entities.add_instance(definition, Geom::Transformation.new)
      instance.name = "PT_#{generator.upcase}"
      output_path = File.join(output_dir, file_name)
      raise "failed to save #{file_name}" unless model.save(output_path)
      bounds = instance.bounds
      records << {
        'generator' => generator,
        'file_name' => file_name,
        'size_bytes' => File.size(output_path),
        'sha256' => Digest::SHA256.file(output_path).hexdigest.upcase,
        'bounds_m' => [
          (bounds.width.to_f / 1.m.to_f).round(4),
          (bounds.height.to_f / 1.m.to_f).round(4),
          (bounds.depth.to_f / 1.m.to_f).round(4)
        ]
      }
    end
    File.write(report_path, JSON.pretty_generate('status' => 'PASS', 'assets' => records))
  rescue StandardError => error
    File.write(report_path, JSON.pretty_generate(
      'status' => 'FAIL',
      'error_class' => error.class.name,
      'error_message' => error.message,
      'backtrace' => error.backtrace&.first(12),
      'completed_assets' => records
    ))
  ensure
    UI.start_timer(1.0, false) { Sketchup.quit }
  end
end
