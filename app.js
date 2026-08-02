// Videasy Pure Custom Player with Transparent Glass Controls & Real-Time Downloader
let hlsInstance = null;
let activeSources = [];
let currentSourceIndex = 0;
let currentMediaId = null;
let mediaType = 'movie';

// DOM Elements
const playerContainer = document.getElementById('player-container');
const videoPlayer = document.getElementById('video-player');
const customControls = document.getElementById('custom-controls');
const topHeaderBar = document.getElementById('top-header-bar');
const mediaTitle = document.getElementById('media-title');
const mediaInfoBadge = document.getElementById('media-info-badge');

const playerLoading = document.getElementById('player-loading');
const playerError = document.getElementById('player-error');
const errorMessage = document.getElementById('error-message');

const playPauseBtn = document.getElementById('play-pause-btn');
const currentTimeEl = document.getElementById('current-time');
const durationTimeEl = document.getElementById('duration-time');

const progressContainer = document.getElementById('progress-container');
const progressFill = document.getElementById('progress-fill');
const bufferFill = document.getElementById('buffer-fill');
const progressScrubber = document.getElementById('progress-scrubber');
const progressTooltip = document.getElementById('progress-tooltip');

const qualitySelect = document.getElementById('quality-select');
const audioSelect = document.getElementById('audio-select');
const subtitleSelect = document.getElementById('subtitle-select');
const speedSelect = document.getElementById('speed-select');
const volumeSlider = document.getElementById('volume-slider');
const muteBtn = document.getElementById('mute-btn');

let autohideTimer = null;

// Logger
function logConsole(msg) {
    console.log(`[Player] ${msg}`);
}

let currentSeason = 1;
let currentEpisode = 1;

const tvControlsGroup = document.getElementById('tv-controls-group');
const seasonSelect = document.getElementById('season-select');
const episodeSelect = document.getElementById('episode-select');

let startTimeInSeconds = 0;

function parseTimeParam(val) {
    if (!val) return 0;
    val = val.toString().trim().toLowerCase();
    
    if (val.includes(':')) {
        const parts = val.split(':').map(p => parseFloat(p) || 0);
        if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
        if (parts.length === 2) return parts[0] * 60 + parts[1];
    }
    
    let total = 0;
    const hMatch = val.match(/(\d+)h/);
    const mMatch = val.match(/(\d+)m/);
    const sMatch = val.match(/(\d+)s/);
    
    if (hMatch) total += parseInt(hMatch[1]) * 3600;
    if (mMatch) total += parseInt(mMatch[1]) * 60;
    if (sMatch) total += parseInt(sMatch[1]);
    if (hMatch || mMatch || sMatch) return total;
    
    return parseFloat(val) || 0;
}

// URL Route Parser
function parseCurrentURL() {
    const path = window.location.pathname;
    const urlParams = new URLSearchParams(window.location.search);
    const hash = window.location.hash;

    if (path.startsWith('/movie/')) {
        const parts = path.split('/movie/')[1].split('/');
        if (parts[0]) currentMediaId = parts[0];
        mediaType = 'movie';
    } else if (path.startsWith('/tv/')) {
        const parts = path.split('/tv/')[1].split('/');
        if (parts[0]) currentMediaId = parts[0];
        if (parts[1]) currentSeason = parseInt(parts[1]) || 1;
        if (parts[2]) currentEpisode = parseInt(parts[2]) || 1;
        mediaType = 'tv';
    } else {
        if (urlParams.get('id')) currentMediaId = urlParams.get('id');
        if (urlParams.get('type')) mediaType = urlParams.get('type');
        if (urlParams.get('season')) currentSeason = parseInt(urlParams.get('season')) || 1;
        if (urlParams.get('episode')) currentEpisode = parseInt(urlParams.get('episode')) || 1;
    }

    const timeRaw = urlParams.get('t') || urlParams.get('time') || (hash.startsWith('#t=') ? hash.substring(3) : null);
    if (timeRaw) {
        startTimeInSeconds = parseTimeParam(timeRaw);
    }
}

function handleSeasonChange(val) {
    currentSeason = parseInt(val) || 1;
    updateURLAndPlay();
}

function handleEpisodeChange(val) {
    currentEpisode = parseInt(val) || 1;
    updateURLAndPlay();
}

function updateURLAndPlay() {
    let newUrl = '/';
    if (mediaType === 'tv') {
        newUrl = `/tv/${currentMediaId}/${currentSeason}/${currentEpisode}`;
    } else {
        newUrl = `/movie/${currentMediaId}`;
    }
    window.history.pushState({ path: newUrl }, '', newUrl);
    resolveAndPlay();
}

function populateSeasonOptions(total = 10) {
    if (!seasonSelect) return;
    seasonSelect.innerHTML = '';
    for (let i = 1; i <= Math.max(total, currentSeason); i++) {
        const opt = document.createElement('option');
        opt.value = i;
        opt.innerText = `Season ${i}`;
        if (i === currentSeason) opt.selected = true;
        seasonSelect.appendChild(opt);
    }
}

function populateEpisodeOptions(total = 24) {
    if (!episodeSelect) return;
    episodeSelect.innerHTML = '';
    for (let i = 1; i <= Math.max(total, currentEpisode); i++) {
        const opt = document.createElement('option');
        opt.value = i;
        opt.innerText = `Episode ${i}`;
        if (i === currentEpisode) opt.selected = true;
        episodeSelect.appendChild(opt);
    }
}



// -------------------------------------------------------------
// RESOLVE & LOAD VIDEASY STREAM
// -------------------------------------------------------------
async function resolveAndPlay() {
    playerError.classList.add('hidden');
    playerLoading.classList.remove('hidden');

    parseCurrentURL();

    if (!currentMediaId) {
        playerLoading.innerHTML = `
            <div class="loading-text">
                <span style="font-size:18px; font-weight:700;">OFC Movies Player Ready</span>
                <p style="margin-top:8px; color:#aaa;">Please provide a media URL request (e.g. /movie/550 or /tv/46260/1/1)</p>
            </div>
        `;
        mediaTitle.innerText = "OFC Movies Stream";
        return;
    }

    if (tvControlsGroup) {
        tvControlsGroup.classList.toggle('hidden', mediaType !== 'tv');
    }

    if (mediaType === 'tv') {
        populateSeasonOptions(10);
        populateEpisodeOptions(24);
    }

    logConsole(`Resolving stream for ${mediaType} ${currentMediaId} (S:${currentSeason} E:${currentEpisode})...`);

    try {
        const fetchUrl = mediaType === 'tv'
            ? `/api/resolve?tmdbId=${currentMediaId}&type=tv&season=${currentSeason}&episode=${currentEpisode}`
            : `/api/resolve?tmdbId=${currentMediaId}&type=movie`;

        const resp = await fetch(fetchUrl);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        if (!data.success || !data.sources || data.sources.length === 0) {
            logConsole("No direct HLS source found.");
            showPlayerError("Could not resolve stream source. Please retry.");
            return;
        }

        // Update Title, Badge and Thumbnail Poster
        if (data.title) {
            const epBadge = mediaType === 'tv' ? ` (S${currentSeason} E${currentEpisode})` : '';
            mediaTitle.innerText = `${data.title}${epBadge}${data.year ? ` (${data.year})` : ''}`;
            if (mediaInfoBadge) {
                mediaInfoBadge.innerHTML = `<i class="fa-solid fa-film"></i> OFC Movies`;
            }
        }

        // Show TMDB backdrop/poster as thumbnail before playback
        const thumbUrl = data.backdrop_path
            ? `https://image.tmdb.org/t/p/w1280${data.backdrop_path}`
            : data.poster_path
            ? `https://image.tmdb.org/t/p/w780${data.poster_path}`
            : null;

        const existingThumb = document.getElementById('thumbnail-overlay');
        if (existingThumb) existingThumb.remove();

        if (thumbUrl) {
            const thumbDiv = document.createElement('div');
            thumbDiv.id = 'thumbnail-overlay';
            thumbDiv.style.cssText = `
                position:absolute; inset:0; z-index:5;
                background: url('${thumbUrl}') center/cover no-repeat;
                transition: opacity 0.5s ease;
                cursor: pointer;
            `;
            // Big play icon on top of thumbnail
            thumbDiv.innerHTML = `<div style="
                position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
                background: rgba(0,0,0,0.3);
            "><div style="
                width:72px; height:72px; border-radius:50%;
                background: rgba(255,255,255,0.15); backdrop-filter:blur(8px);
                border:2px solid rgba(255,255,255,0.4);
                display:flex; align-items:center; justify-content:center;
                font-size:28px; color:#fff; padding-left:5px;
            ">▶</div></div>`;
            thumbDiv.addEventListener('click', () => {
                thumbDiv.style.opacity = '0';
                setTimeout(() => thumbDiv.remove(), 500);
            });
            playerContainer.appendChild(thumbDiv);
        }

        restoreCustomPlayer();
        activeSources = data.sources;
        currentSourceIndex = 0;
        
        updateQualityDropdown(activeSources);
        playSource(activeSources[0].url, 0);

        playerLoading.classList.add('hidden');

    } catch (err) {
        logConsole(`Resolution error: ${err.message}`);
        showPlayerError("Unable to load stream. Please retry.");
    }
}

function showPlayerError(msg) {
    if (playerLoading) playerLoading.classList.add('hidden');
    if (playerError) {
        const msgEl = document.getElementById('error-message');
        if (msgEl) msgEl.innerText = msg;
        playerError.classList.remove('hidden');
    }
}

function restoreCustomPlayer() {
    if (videoPlayer) {
        videoPlayer.classList.remove('hidden');
    }
    if (customControls) {
        customControls.classList.remove('hidden');
    }
}



// -------------------------------------------------------------
// PLAY HLS STREAM NATIVELY OR VIA STREAM PLAYER
// -------------------------------------------------------------
function playSource(streamUrl, sourceIndex = 0) {
    currentSourceIndex = sourceIndex;
    logConsole(`Playing source index ${sourceIndex}: ${streamUrl}`);

    if (!activeSources || activeSources.length === 0) {
        qualitySelect.innerHTML = '<option value="-1">Auto Quality</option>';
    }
    audioSelect.innerHTML = '<option value="-1">Default Audio</option>';
    subtitleSelect.innerHTML = '<option value="-1">Subtitles Off</option>';

    const activeSrcObj = activeSources && activeSources[sourceIndex];
    const isEmbed = (activeSrcObj && activeSrcObj.is_embed) || 
                    streamUrl.includes('videasy.to') || 
                    streamUrl.includes('/embed') || 
                    !streamUrl.includes('.m3u8');

    let existingIframe = document.getElementById('embed-iframe');

    if (isEmbed) {
        if (hlsInstance) {
            hlsInstance.destroy();
            hlsInstance = null;
        }
        if (videoPlayer) {
            videoPlayer.classList.add('hidden');
            try { videoPlayer.pause(); } catch(e) {}
        }
        if (customControls) {
            customControls.classList.add('hidden');
        }

        const thumb = document.getElementById('thumbnail-overlay');
        if (thumb) thumb.remove();

        if (!existingIframe) {
            existingIframe = document.createElement('iframe');
            existingIframe.id = 'embed-iframe';
            existingIframe.style.cssText = 'position:absolute; inset:0; width:100%; height:100%; border:none; z-index:10; background:#000;';
            existingIframe.allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture';
            existingIframe.setAttribute('allowfullscreen', 'true');
            existingIframe.src = streamUrl;
            playerContainer.appendChild(existingIframe);
        } else {
            existingIframe.classList.remove('hidden');
            existingIframe.src = streamUrl;
        }

        if (playerLoading) playerLoading.classList.add('hidden');
        return;
    }

    // Direct HLS playback
    if (existingIframe) existingIframe.remove();
    if (videoPlayer) {
        videoPlayer.classList.remove('hidden');
    }
    if (customControls) {
        customControls.classList.remove('hidden');
    }

    if (Hls.isSupported()) {
        if (hlsInstance) hlsInstance.destroy();

        const isWorkersDev = streamUrl.includes('workers.dev');

        hlsInstance = new Hls({
            enableWorker: true,
            lowLatencyMode: false,
            startLevel: -1,
            maxBufferLength: 30,
            maxMaxBufferLength: 60,
            maxBufferSize: 60 * 1024 * 1024,
            manifestLoadingTimeOut: 25000,
            fragLoadingTimeOut: 25000,
            levelLoadingTimeOut: 25000,
            xhrSetup: function(xhr) {
                xhr.withCredentials = false;
            }
        });

        hlsInstance.loadSource(streamUrl);
        hlsInstance.attachMedia(videoPlayer);

        function populateQualityLevels() {
            if (activeSources && activeSources.length > 1) return;
            if (!hlsInstance || !hlsInstance.levels || hlsInstance.levels.length === 0) return;

            const levels = hlsInstance.levels;
            const validLevels = [];
            const seenHeights = new Set();

            levels.forEach((lvl, idx) => {
                if (lvl && lvl.height && lvl.height > 0 && !seenHeights.has(lvl.height)) {
                    seenHeights.add(lvl.height);
                    validLevels.push({ index: idx, height: lvl.height });
                }
            });

            validLevels.sort((a, b) => b.height - a.height);

            const curVal = qualitySelect.value;
            qualitySelect.innerHTML = '';

            if (validLevels.length > 1) {
                const autoOpt = document.createElement('option');
                autoOpt.value = "-1";
                autoOpt.innerText = "Auto Quality";
                if (parseInt(curVal) === -1) autoOpt.selected = true;
                qualitySelect.appendChild(autoOpt);

                validLevels.forEach(lvl => {
                    const opt = document.createElement('option');
                    opt.value = lvl.index;
                    opt.innerText = `${lvl.height}p HD`;
                    if (parseInt(curVal) === lvl.index) opt.selected = true;
                    qualitySelect.appendChild(opt);
                });
            } else if (validLevels.length === 1) {
                const opt = document.createElement('option');
                opt.value = validLevels[0].index;
                opt.innerText = `${validLevels[0].height}p HD`;
                opt.selected = true;
                qualitySelect.appendChild(opt);
            } else {
                const opt = document.createElement('option');
                opt.value = "-1";
                opt.innerText = "Auto Quality";
                qualitySelect.appendChild(opt);
            }
        }

        hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
            logConsole("HLS Manifest Parsed.");
            // Remove thumbnail overlay now that video is ready
            const thumb = document.getElementById('thumbnail-overlay');
            if (thumb) {
                thumb.style.opacity = '0';
                setTimeout(() => thumb.remove(), 500);
            }
            if (startTimeInSeconds > 0) {
                videoPlayer.currentTime = startTimeInSeconds;
                startTimeInSeconds = 0;
            }
            const playPromise = videoPlayer.play();
            if (playPromise !== undefined) {
                playPromise.then(() => {
                    logConsole("Playback started successfully.");
                }).catch((err) => {
                    logConsole("Autoplay prevented, retrying muted: " + err.message);
                    videoPlayer.muted = true;
                    videoPlayer.play().catch(() => {});
                });
            }
            updateTimeline();
            updatePlayPauseState();
            populateQualityLevels();

            // Populate Audio Tracks natively from HLS stream
            function populateAudioTracks() {
                if (!audioSelect) return;
                audioSelect.innerHTML = '';
                if (hlsInstance && hlsInstance.audioTracks && hlsInstance.audioTracks.length > 1) {
                    hlsInstance.audioTracks.forEach((tr, idx) => {
                        const opt = document.createElement('option');
                        opt.value = idx;
                        opt.innerText = tr.name || tr.lang || `Audio Track ${idx + 1}`;
                        if (hlsInstance.audioTrack === idx) opt.selected = true;
                        audioSelect.appendChild(opt);
                    });
                } else {
                    const tracks = [
                        { val: '0', label: 'Japanese (Original Audio)' },
                        { val: '1', label: 'English Dub' },
                        { val: '2', label: 'Hindi Dual Audio' }
                    ];
                    tracks.forEach((t, i) => {
                        const opt = document.createElement('option');
                        opt.value = t.val;
                        opt.innerText = t.label;
                        if (i === 0) opt.selected = true;
                        audioSelect.appendChild(opt);
                    });
                }
            }
            populateAudioTracks();
            hlsInstance.on(Hls.Events.AUDIO_TRACKS_UPDATED, populateAudioTracks);

            // Populate Subtitles
            if (hlsInstance.subtitleTracks && hlsInstance.subtitleTracks.length > 0) {
                subtitleSelect.innerHTML = '<option value="-1">Subtitles Off</option>';
                
                hlsInstance.subtitleTracks.forEach((tr, idx) => {
                    const opt = document.createElement('option');
                    opt.value = idx;
                    opt.innerText = tr.name || tr.lang || `Sub ${idx + 1}`;
                    subtitleSelect.appendChild(opt);
                });
            }
        });

        hlsInstance.on(Hls.Events.LEVEL_LOADED, (evt, data) => {
            if (data && data.details && data.details.totalduration) {
                durationTimeEl.innerText = formatTime(data.details.totalduration);
            }
            updateTimeline();
            populateQualityLevels();
        });
        hlsInstance.on(Hls.Events.LEVEL_SWITCHED, populateQualityLevels);

        // Error Fallback
        let triedProxy = false;
        let directRetries = 0;
        hlsInstance.on(Hls.Events.ERROR, (evt, data) => {
            // Non-fatal: just recover silently
            if (!data.fatal) {
                if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
                    hlsInstance.recoverMediaError();
                }
                return;
            }

            // workers.dev URLs: NEVER proxy — Cloudflare blocks server requests
            if (isWorkersDev) {
                if (directRetries < 2) {
                    directRetries++;
                    logConsole(`workers.dev retry ${directRetries}...`);
                    setTimeout(() => { hlsInstance.loadSource(streamUrl); }, 1500 * directRetries);
                } else if (currentSourceIndex + 1 < activeSources.length) {
                    playSource(activeSources[currentSourceIndex + 1].url, currentSourceIndex + 1);
                } else {
                    // Show retry button — do NOT call resolveAndPlay() (causes restart loop)
                    showPlayerError('Stream failed. Click Retry to reload.');
                }
                return;
            }

            // Normal CDN URLs: try proxy fallback first
            if (!triedProxy && streamUrl && !streamUrl.includes('/api/m3u8-proxy')) {
                triedProxy = true;
                const proxiedUrl = `/api/m3u8-proxy?url=${encodeURIComponent(streamUrl)}`;
                logConsole(`Direct load failed, trying proxy fallback: ${proxiedUrl}`);
                hlsInstance.loadSource(proxiedUrl);
            } else if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
                logConsole("Network error, recovering...");
                hlsInstance.startLoad();
            } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
                logConsole("Media error, recovering...");
                hlsInstance.recoverMediaError();
            } else if (currentSourceIndex + 1 < activeSources.length) {
                const nextIdx = currentSourceIndex + 1;
                logConsole(`Fallback to source ${nextIdx + 1}`);
                playSource(activeSources[nextIdx].url, nextIdx);
            } else {
                logConsole("All HLS sources exhausted.");
                showPlayerError("Stream connection failed. Please retry.");
            }
        });
    } else if (videoPlayer.canPlayType('application/vnd.apple.mpegurl')) {
        videoPlayer.src = streamUrl;
        videoPlayer.play().catch(() => {});
    }
}

// -------------------------------------------------------------
// QUALITY DROPDOWN POPULATOR
// -------------------------------------------------------------
function updateQualityDropdown(sources) {
    if (!qualitySelect) return;
    qualitySelect.innerHTML = '';

    if (!sources || sources.length === 0) {
        qualitySelect.innerHTML = '<option value="-1">Auto Quality</option>';
        return;
    }

    sources.forEach((src, idx) => {
        const opt = document.createElement('option');
        opt.value = `src:${idx}`;
        const qLabel = src.quality ? src.quality.trim() : `Quality ${idx + 1}`;
        opt.innerText = qLabel;
        if (idx === currentSourceIndex) opt.selected = true;
        qualitySelect.appendChild(opt);
    });
}

// -------------------------------------------------------------
// PLAYER INTERACTIVE CONTROLS & TIMELINE
// -------------------------------------------------------------

function togglePlay() {
    if (videoPlayer.paused) {
        videoPlayer.play();
    } else {
        videoPlayer.pause();
    }
    updatePlayPauseState();
}

function updatePlayPauseState() {
    const isPaused = videoPlayer.paused;
    if (playPauseBtn) {
        playPauseBtn.innerHTML = isPaused ? '<i class="fa-solid fa-play"></i>' : '<i class="fa-solid fa-pause"></i>';
    }
    showControls();
}

videoPlayer.addEventListener('play', updatePlayPauseState);
videoPlayer.addEventListener('pause', updatePlayPauseState);

// Skip Forward / Backward
function skipTime(seconds) {
    if (!videoPlayer.duration) return;
    videoPlayer.currentTime = Math.min(Math.max(videoPlayer.currentTime + seconds, 0), videoPlayer.duration);
}

// Time & Instant Progress Update
function updateTimeline() {
    if (!videoPlayer.duration || isNaN(videoPlayer.duration)) return;
    const cur = videoPlayer.currentTime || 0;
    const dur = videoPlayer.duration;

    const pct = (cur / dur) * 100;
    progressFill.style.width = `${pct}%`;
    progressScrubber.style.left = `${pct}%`;

    currentTimeEl.innerText = formatTime(cur);
    durationTimeEl.innerText = formatTime(dur);

    // Buffer bar
    if (videoPlayer.buffered && videoPlayer.buffered.length > 0) {
        const bufEnd = videoPlayer.buffered.end(videoPlayer.buffered.length - 1);
        bufferFill.style.width = `${(bufEnd / dur) * 100}%`;
    }
}

videoPlayer.addEventListener('timeupdate', updateTimeline);
videoPlayer.addEventListener('loadedmetadata', updateTimeline);
videoPlayer.addEventListener('durationchange', updateTimeline);
videoPlayer.addEventListener('canplay', updateTimeline);

function formatTime(seconds) {
    if (isNaN(seconds)) return "00:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
}

function seekVideo(e) {
    const rect = progressContainer.getBoundingClientRect();
    const pos = (e.clientX - rect.left) / rect.width;
    videoPlayer.currentTime = Math.min(Math.max(pos * videoPlayer.duration, 0), videoPlayer.duration);
}

function updateProgressTooltip(e) {
    if (!videoPlayer.duration) return;
    const rect = progressContainer.getBoundingClientRect();
    const pos = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    const hoverTime = pos * videoPlayer.duration;
    
    progressTooltip.innerText = formatTime(hoverTime);
    progressTooltip.style.left = `${pos * 100}%`;
}

function hideProgressTooltip() {
    // Hidden via CSS on mouseleave
}

// Volume Controls
function changeVolume(val) {
    videoPlayer.volume = parseFloat(val);
    videoPlayer.muted = (val == 0);
    updateVolumeIcon();
}

function toggleMute() {
    videoPlayer.muted = !videoPlayer.muted;
    volumeSlider.value = videoPlayer.muted ? 0 : videoPlayer.volume;
    updateVolumeIcon();
}

function updateVolumeIcon() {
    if (videoPlayer.muted || videoPlayer.volume == 0) {
        muteBtn.innerHTML = '<i class="fa-solid fa-volume-xmark"></i>';
    } else if (videoPlayer.volume < 0.5) {
        muteBtn.innerHTML = '<i class="fa-solid fa-volume-low"></i>';
    } else {
        muteBtn.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
    }
}

// Quality & Audio Selectors
function changeQuality(val) {
    if (typeof val === 'string' && val.startsWith('src:')) {
        const idx = parseInt(val.split(':')[1]);
        if (activeSources && activeSources[idx]) {
            playSource(activeSources[idx].url, idx);
        }
    } else if (hlsInstance) {
        hlsInstance.currentLevel = parseInt(val);
    }
}

function changeAudioTrack(val) {
    if (hlsInstance) {
        hlsInstance.audioTrack = parseInt(val);
    }
}

function changeSubtitle(idx) {
    if (hlsInstance) hlsInstance.subtitleTrack = parseInt(idx);
}

function changeSpeed(rate) {
    videoPlayer.playbackRate = parseFloat(rate);
}

// Picture-in-Picture
async function togglePiP() {
    try {
        if (document.pictureInPictureElement) {
            await document.exitPictureInPicture();
        } else if (document.pictureInPictureEnabled) {
            await videoPlayer.requestPictureInPicture();
        }
    } catch (err) {
        logConsole(`PiP error: ${err.message}`);
    }
}

// Fullscreen
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        playerContainer.requestFullscreen().catch(() => {});
        playerContainer.classList.add('fullscreen');
    } else {
        document.exitFullscreen().catch(() => {});
        playerContainer.classList.remove('fullscreen');
    }
}

// Download Button
function triggerDownload() {
    const src = activeSources[currentSourceIndex] || activeSources[0];
    const title = mediaTitle ? mediaTitle.innerText.replace(/[^a-zA-Z0-9_\-]/g, '_') : `OFC_Movies_Video_${currentMediaId}`;
    const downloadUrl = src 
        ? `/api/download-video?url=${encodeURIComponent(src.url)}&title=${encodeURIComponent(title)}`
        : `/dwn/${currentMediaId}`;
    window.location.href = downloadUrl;
}

// Keyboard Shortcuts
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

    if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
    } else if (e.code === 'KeyF') {
        toggleFullscreen();
    } else if (e.code === 'KeyM') {
        toggleMute();
    } else if (e.code === 'KeyP') {
        togglePiP();
    } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        skipTime(-10);
    } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        skipTime(10);
    } else if (e.code === 'ArrowUp') {
        e.preventDefault();
        changeVolume(Math.min(videoPlayer.volume + 0.1, 1));
    } else if (e.code === 'ArrowDown') {
        e.preventDefault();
        changeVolume(Math.max(videoPlayer.volume - 0.1, 0));
    }
    showControls();
});

// Transparent Glass Controls Autohide & Toggle System
let controlsVisible = true;

function toggleControls() {
    if (controlsVisible) {
        if (customControls) customControls.classList.add('autohide');
        if (topHeaderBar) topHeaderBar.classList.add('autohide');
        controlsVisible = false;
        clearTimeout(autohideTimer);
    } else {
        showControls();
    }
}

function showControls() {
    if (customControls) customControls.classList.remove('autohide');
    if (topHeaderBar) topHeaderBar.classList.remove('autohide');
    controlsVisible = true;

    clearTimeout(autohideTimer);
    if (!videoPlayer.paused) {
        autohideTimer = setTimeout(() => {
            if (customControls) customControls.classList.add('autohide');
            if (topHeaderBar) topHeaderBar.classList.add('autohide');
            controlsVisible = false;
        }, 3200);
    }
}

// VIDEO CLICK: toggle controls visibility (hide/show)
// Play/pause is handled by the play button & spacebar
if (videoPlayer) {
    videoPlayer.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleControls();
    });
}

playerContainer.addEventListener('mousemove', showControls);
playerContainer.addEventListener('touchstart', showControls);

// Auto initialize
window.addEventListener('DOMContentLoaded', () => {
    resolveAndPlay();
});

