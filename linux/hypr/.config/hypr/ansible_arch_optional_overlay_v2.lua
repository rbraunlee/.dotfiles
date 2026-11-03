-- ansible_arch.hyprland_optional_overlay/v2
local home = assert(os.getenv("HOME"), "HOME is required for optional overlay")
local overlay_path = home .. "/.config/ansible_arch/hyprland-optional.lua"
-- No generated overlay means standalone dotfiles retain their established
-- Voxtype startup, shortcut, and NVIDIA environment behavior.
local defaults = {
	voxtype_enabled = true,
	nvidia_environment = true,
}

local overlay_file = io.open(overlay_path, "r")
if not overlay_file then
	return defaults
end
overlay_file:close()

local loaded, overlay = pcall(dofile, overlay_path)
if not loaded or type(overlay) ~= "table" then
	error("invalid ansible_arch optional overlay")
end
if type(overlay.voxtype_enabled) ~= "boolean"
	or type(overlay.nvidia_environment) ~= "boolean" then
	error("invalid ansible_arch optional overlay values")
end

return overlay
