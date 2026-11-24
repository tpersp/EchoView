-- Fixed-format events only: never include source URLs or page credentials.
local function ready()
    local duration = mp.get_property_number("duration")
    mp.msg.info("ECHOVIEW_PLAYBACK_STARTED|" .. (duration and tostring(duration) or "N/A"))
end
mp.register_event("playback-restart", ready)
mp.register_event("file-loaded", function()
    if mp.get_property_bool("pause", false) then ready() end
end)
