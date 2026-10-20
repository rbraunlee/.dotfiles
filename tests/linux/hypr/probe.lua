-- Hyprland API boundary: never execute a shell command or start a desktop process.
local config_path, case = ...
local binds = {}
local startup = {}
local launched = {}
local env = {}
local monitor, settings, device
local curves, animations, rules = 0, 0, 0

local function action(kind, value)
    return { kind = kind, value = value }
end

hl = {
    monitor = function(options) monitor = options end,
    on = function(event, callback)
        assert(event == "hyprland.start")
        startup[#startup + 1] = callback
    end,
    exec_cmd = function(command) launched[#launched + 1] = command end,
    env = function(name, value) env[name] = value end,
    config = function(options) settings = options end,
    curve = function() curves = curves + 1 end,
    animation = function() animations = animations + 1 end,
    device = function(options) device = options end,
    bind = function(key, dispatch)
        binds[#binds + 1] = { key = key, dispatch = dispatch }
    end,
    window_rule = function() rules = rules + 1 end,
    dsp = {
        exec_cmd = function(command) return action("command", command) end,
        focus = function(options) return action("focus", options) end,
        exit = function() return action("exit") end,
        window = {
            close = function() return action("close") end,
            float = function(options) return action("float", options) end,
            pseudo = function() return action("pseudo") end,
            fullscreen = function() return action("fullscreen") end,
            move = function(options) return action("move", options) end,
            drag = function() return action("drag") end,
            resize = function() return action("resize") end,
        },
    },
}

assert(loadfile(config_path))()

if case == "screenshot" then
    local screenshots = {}
    for _, binding in ipairs(binds) do
        if binding.key == "SUPER + CTRL + SHIFT + s" then
            screenshots[#screenshots + 1] = binding.dispatch
        end
    end
    assert(#screenshots == 1, "expected exactly one existing screenshot shortcut, got " .. #screenshots)
    assert(screenshots[1].kind == "command", "screenshot must dispatch a command")
    assert(screenshots[1].value == "flameshot gui",
        "expected interactive Flameshot dispatch, got: " .. tostring(screenshots[1].value))
elseif case == "startup" then
    assert(#startup == 1, "startup handler changed")
    startup[1]()
    assert(#launched == 6, "autostart commands changed")
    assert(launched[1] == "waybar" and launched[2] == "hyprpaper"
        and launched[3] == "mako"
        and launched[4] == 'gsettings set org.gnome.desktop.interface color-scheme "prefer-dark"'
        and launched[5] == "/usr/lib/polkit-kde-authentication-agent-1",
        "autostart must not gain capture, fallback or lock commands")
    assert(env.XCURSOR_SIZE == "24" and env.HYPRCURSOR_SIZE == "24"
        and env.LIBVA_DRIVER_NAME == "nvidia" and env.__GLX_VENDOR_LIBRARY_NAME == "nvidia",
        "environment changed")
    local count = 0
    for _ in pairs(env) do count = count + 1 end
    assert(count == 4, "unexpected global environment override")
elseif case == "voxtype_startup" then
    assert(#startup == 1 and #launched == 0, "config load/reload must not launch a daemon")
    startup[1]()
    assert(#launched == 6, "expected one new startup dispatch")
    for i = 1, 5 do
        assert(not launched[i]:find("voxtype") and not launched[i]:find("systemctl"),
            "existing autostart dispatches changed")
    end
    print(launched[6])
elseif case == "desktop" then
    local by_key = {}
    for _, binding in ipairs(binds) do
        assert(not by_key[binding.key], "duplicate key: " .. binding.key)
        by_key[binding.key] = binding.dispatch
    end
    assert(#binds == 42, "keybindings added or removed: " .. #binds)
    assert(by_key["SUPER + T"].value == "ghostty")
    assert(by_key["SUPER + E"].value == "dolphin")
    assert(by_key["SUPER + SPACE"].value == "wofi --show drun")
    assert(by_key["SUPER + Q"].kind == "close")
    assert(by_key["SUPER + h"].value.direction == "left")
    assert(by_key["SUPER + SHIFT + j"].value.direction == "down")
    assert(by_key["SUPER + 0"].value.workspace == 10)
    assert(by_key["SUPER + SHIFT + 0"].value.workspace == 10
        and by_key["SUPER + SHIFT + 0"].value.follow == true)
    assert(by_key["SUPER + mouse:272"].kind == "drag")
    assert(by_key["SUPER + mouse:273"].kind == "resize")
    assert(monitor.mode == "preferred" and monitor.position == "auto"
        and monitor.scale == "auto", "monitor settings changed")
    assert(settings.general.layout == "dwindle" and settings.general.gaps_in == 2
        and settings.general.col.active_border == "rgba(204,36,29,1.0)",
        "layout or theme changed")
    assert(settings.input.kb_layout == "us" and settings.input.touchpad.natural_scroll == false,
        "input settings changed")
    assert(device.name == "epic-mouse-v1" and device.sensitivity == -0.5,
        "device settings changed")
    assert(curves == 5 and animations == 10 and rules == 4,
        "animations or window rules changed")
elseif case == "dictation" then
    local by_key = {}
    for _, binding in ipairs(binds) do
        assert(not by_key[binding.key], "duplicate key: " .. binding.key)
        by_key[binding.key] = binding.dispatch
    end
    local toggle = by_key["SUPER + CTRL + d"]
    assert(toggle and toggle.kind == "command", "missing non-conflicting dictation shortcut")
    assert(toggle.value == "voxtype record toggle", "shortcut must toggle without submitting")
else
    error("unknown probe case: " .. tostring(case))
end
