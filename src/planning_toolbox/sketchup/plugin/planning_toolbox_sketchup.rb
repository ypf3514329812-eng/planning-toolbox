# frozen_string_literal: true

require 'sketchup.rb'
require 'extensions.rb'

module PlanningToolbox
  EXTENSION = SketchupExtension.new(
    'Planning Toolbox 模型交接',
    'planning_toolbox_sketchup/main'
  )
  EXTENSION.description = '把 Planning Toolbox 的 .ptsu.json 交接文件生成分层、可编辑的 SketchUp 模型。'
  EXTENSION.version = '0.61.1'
  EXTENSION.creator = 'Planning Toolbox'
  EXTENSION.copyright = '2026 Planning Toolbox'

  Sketchup.register_extension(EXTENSION, true)
end
