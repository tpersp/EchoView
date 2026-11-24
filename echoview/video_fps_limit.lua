-- Limit rendering work without retiming playback or touching source files.
local label = 'echoview_fps_limit'

local function apply_limit(_, fps)
    local active = false
    for _, filter in ipairs(mp.get_property_native('vf', {})) do
        if filter.label == label then active = true end
    end
    local needed = type(fps) == 'number' and fps > 24
    if needed and not active then
        local ok, err = mp.command_native({'vf', 'add', '@' .. label .. ':lavfi=[fps=fps=24]'})
        if not ok then mp.msg.warn('Frame-rate limit unavailable; keeping native playback: ' .. tostring(err)) end
    elseif not needed and active then
        mp.command_native({'vf', 'remove', '@' .. label})
    end
end

-- Re-evaluate on file/track changes; unknown frame rates stay native.
mp.observe_property('container-fps', 'number', apply_limit)
