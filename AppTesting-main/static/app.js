// ── STATE ──
let selectedImages = [];   // array of File objects (photos)
let selectedAudio  = null;
let selectedVideo  = null;
const MAX_PHOTOS   = 5;
const MAX_VIDEO_SEC = 50;
let isRecording    = false;
let mediaRecorder  = null;
let audioChunks    = [];
let recInterval    = null;
let recSeconds     = 0;
let cameraStream   = null;
let userLocation   = null;
let locationAddr   = '';
let locationSource = null; // 'camera' | 'upload' | 'gps'
let userProfile    = null;

// ── ONBOARDING ──
function loadProfile() {
  try { userProfile = JSON.parse(localStorage.getItem('tampines_profile') || 'null'); } catch(e){}
  if (!userProfile || !userProfile.phone || !userProfile.name) {
    const onboardScreen = document.getElementById('onboardScreen');
    if (onboardScreen) onboardScreen.classList.add('show');
  } else { updateHeaderProfile(); }
}

function saveProfile() {
  const nameEl    = document.getElementById('onboardName');
  const phoneEl   = document.getElementById('onboardPhone');
  const addressEl = document.getElementById('onboardAddress');
  const err       = document.getElementById('onboardError');
  if (!nameEl || !phoneEl) return;
  const name    = nameEl.value.trim();
  const phone   = phoneEl.value.trim().replace(/\s/g,'');
  const address = addressEl ? addressEl.value.trim() : '';
  if (!name || !/^\d{8}$/.test(phone)) { if(err) err.classList.add('show'); return; }
  if (err) err.classList.remove('show');
  userProfile = { name, phone: '+65' + phone, homeAddress: address };
  localStorage.setItem('tampines_profile', JSON.stringify(userProfile));
  const onboardScreen = document.getElementById('onboardScreen');
  if (onboardScreen) onboardScreen.classList.remove('show');
  updateHeaderProfile();
}

function updateHeaderProfile() {
  if (!userProfile) return;
  const avatarEl = document.getElementById('profileAvatar');
  const nameEl   = document.getElementById('profileName');
  const headerEl = document.getElementById('headerProfile');
  if (!avatarEl || !nameEl || !headerEl) return; // guard: DOM not ready
  const initials = userProfile.name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
  avatarEl.textContent = initials;
  nameEl.textContent   = userProfile.name.split(' ')[0];
  headerEl.style.display = 'flex';
}

function editProfile() {
  if (!userProfile) return;
  const nameEl    = document.getElementById('onboardName');
  const phoneEl   = document.getElementById('onboardPhone');
  const addressEl = document.getElementById('onboardAddress');
  if (nameEl)    nameEl.value    = userProfile.name;
  if (phoneEl)   phoneEl.value   = userProfile.phone.replace('+65','');
  if (addressEl) addressEl.value = userProfile.homeAddress || '';
  const onboardScreen = document.getElementById('onboardScreen');
  if (onboardScreen) onboardScreen.classList.add('show');
}

// ── NAVIGATION ──
function goProfile() { window.location.href = '/profile.html'; }

// ── GPS ──
function startGPS() {
  if (!navigator.geolocation) { setGPS('', 'Location not available', false); return; }
  navigator.geolocation.getCurrentPosition(async pos => {
    // Only store as background fallback — don't override camera-locked location
    if (locationSource !== 'camera') {
      userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      locationSource = 'gps';
      try {
        const res  = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${userLocation.lat}&lon=${userLocation.lng}&format=json`);
        const data = await res.json();
        const parts = (data.display_name || '').split(',');
        locationAddr = parts.slice(0,3).join(',').trim();
        setGPS('found', '📍 ' + locationAddr, true);
      } catch {
        locationAddr = `${userLocation.lat.toFixed(4)}, ${userLocation.lng.toFixed(4)}`;
        setGPS('found', '📍 Location found', true);
      }
    }
  }, () => setGPS('warn', 'Location unavailable — state your block when speaking', false),
  { timeout: 10000, enableHighAccuracy: true });
}

// Lock GPS at the exact moment camera photo is taken
async function lockCameraLocation() {
  return new Promise(resolve => {
    if (!navigator.geolocation) { resolve(); return; }
    setGPS('searching', '📍 Locking location…', false);
    navigator.geolocation.getCurrentPosition(async pos => {
      userLocation  = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      locationSource = 'camera';
      try {
        const res  = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${userLocation.lat}&lon=${userLocation.lng}&format=json`);
        const data = await res.json();
        const parts = (data.display_name || '').split(',');
        locationAddr = parts.slice(0,3).join(',').trim();
        setGPS('found', '📍 ' + locationAddr, true);
      } catch {
        locationAddr = `${userLocation.lat.toFixed(4)}, ${userLocation.lng.toFixed(4)}`;
        setGPS('found', '📍 Location locked', true);
      }
      // Hide upload address strip since we have live location
      const strip = document.getElementById('uploadAddrStrip');
      if (strip) strip.style.display = 'none';
      resolve();
    }, () => {
      // GPS failed — fall back to home address
      setGPS('warn', 'GPS unavailable', false);
      resolve();
    }, { timeout: 8000, enableHighAccuracy: true });
  });
}
function setGPS(cls, text, _found) {
  const dot = document.getElementById('gpsDot');
  if (!dot) return;
  dot.className = 'gps-dot' + (cls ? ' '+cls : '');
  const textEl = document.getElementById('gpsText');
  textEl.textContent = text;
  textEl.className = 'gps-text' + (cls === 'warn' ? ' warn' : '');
}

// ── IMAGE HANDLING ──
function handleImageFile(input) {
  const files = Array.from(input.files); if (!files.length) return;

  const currentCount = selectedImages.filter(Boolean).length;
  const remaining    = MAX_PHOTOS - currentCount;

  if (remaining <= 0) {
    showError('Maximum 5 photos allowed.');
    input.value = ''; return;
  }

  files.slice(0, remaining).forEach(f => addImageToGallery(f));
  if (files.length > remaining)
    showError(`Only ${remaining} more photo(s) added — limit is 5.`);

  document.getElementById('btnCamera').classList.add('done');
  input.value = '';
}
function handleUploadFile(input) {
  const files = Array.from(input.files); if (!files.length) return;
  const vids  = files.filter(f => f.type.startsWith('video/'));
  const imgs  = files.filter(f => !f.type.startsWith('video/'));

  // ── Video: max 1 file, max 50 seconds ──
  if (vids.length) {
    if (selectedVideo) {
      showError('Only 1 video allowed. Remove the current one first.');
      input.value = ''; return;
    }
    const file    = vids[0];
    const tempVid = document.createElement('video');
    tempVid.preload = 'metadata';
    tempVid.onloadedmetadata = () => {
      URL.revokeObjectURL(tempVid.src);
      if (tempVid.duration > MAX_VIDEO_SEC) {
        showError(`Video must be ${MAX_VIDEO_SEC} seconds or less.`);
        input.value = ''; return;
      }
      // ✅ Accepted
      selectedVideo = file;
      const vid = document.getElementById('videoPreview');
      vid.src = URL.createObjectURL(file);
      document.getElementById('videoWrap').style.display = 'block';
      document.getElementById('mediaGallery').classList.add('show');
      document.getElementById('addMorePill').style.display = 'flex';
      document.getElementById('btnUpload').classList.add('done');
    };
    tempVid.src = URL.createObjectURL(file);
  }

  // ── Photos: max 5 total ──
  if (imgs.length) {
    const currentCount = selectedImages.filter(Boolean).length;
    const remaining    = MAX_PHOTOS - currentCount;
    if (remaining <= 0) {
      showError('Maximum 5 photos allowed.');
    } else {
      imgs.slice(0, remaining).forEach(f => addImageToGallery(f));
      if (imgs.length > remaining)
        showError(`Only ${remaining} more photo(s) added — limit is 5.`);
      document.getElementById('btnUpload').classList.add('done');
      const upBadge = document.getElementById('uploadBadge');
      if (upBadge) upBadge.textContent = '✓ Added';
      document.getElementById('btnUpload').querySelector('.act-title').textContent = 'Photo Added';
      document.getElementById('btnUpload').querySelector('.act-sub').textContent   = 'Tap to change';
      document.getElementById('mediaGallery').classList.add('show');
      document.getElementById('addMorePill').style.display = 'flex';
    }
  }

  input.value = '';

  // ── Show address strip ──
  if (locationSource !== 'camera') {
    const strip    = document.getElementById('uploadAddrStrip');
    const addrInput = document.getElementById('uploadAddrInput');
    strip.style.display = 'block';
    if (!addrInput.value && userProfile && userProfile.homeAddress)
      addrInput.value = userProfile.homeAddress;
    locationSource = 'upload';
  }
}

function addImageToGallery(file) {
  selectedImages.push(file);
  const idx = selectedImages.length - 1;
  const url = URL.createObjectURL(file);

  const wrap = document.createElement('div');
  wrap.className = 'thumb-item';
  wrap.id = 'thumb-' + idx;

  const img = document.createElement('img');
  img.src = url; img.alt = 'photo';

  const del = document.createElement('button');
  del.className = 'thumb-del';
  del.textContent = '✕';
  del.onclick = () => removeImage(idx);

  wrap.appendChild(img);
  wrap.appendChild(del);
  document.getElementById('thumbScroll').appendChild(wrap);
  document.getElementById('mediaGallery').classList.add('show');
  document.getElementById('addMorePill').style.display = 'flex';
}

function removeImage(idx) {
  selectedImages[idx] = null;
  const el = document.getElementById('thumb-' + idx);
  if (el) el.remove();
  const remaining = selectedImages.filter(Boolean);
  if (!remaining.length && !selectedVideo) {
    document.getElementById('mediaGallery').classList.remove('show');
    document.getElementById('addMorePill').style.display = 'none';
    document.getElementById('btnCamera').classList.remove('done');
    document.getElementById('btnUpload').classList.remove('done');
  }
}

function clearVideo() {
  selectedVideo = null;
  document.getElementById('videoWrap').style.display = 'none';
  document.getElementById('videoPreview').src = '';
  const remaining = selectedImages.filter(Boolean);
  if (!remaining.length) {
    document.getElementById('mediaGallery').classList.remove('show');
    document.getElementById('addMorePill').style.display = 'none';
    document.getElementById('btnUpload').classList.remove('done');
  }
}

function clearAllMedia() {
  selectedImages = []; selectedVideo = null;
  document.getElementById('thumbScroll').innerHTML = '';
  document.getElementById('videoWrap').style.display = 'none';
  document.getElementById('videoPreview').src = '';
  document.getElementById('mediaGallery').classList.remove('show');
  document.getElementById('addMorePill').style.display = 'none';
  document.getElementById('btnCamera').classList.remove('done');
  document.getElementById('btnUpload').classList.remove('done');
}

// ── CAMERA ──
async function openCamera() {
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video:{facingMode:'environment'}, audio:false });
    document.getElementById('cameraPreview').srcObject = cameraStream;
    document.getElementById('cameraPreview').style.display = 'block';
    document.getElementById('capturedImg').style.display   = 'none';
    document.getElementById('captureBtn').style.display    = 'inline-block';
    document.getElementById('retakeBtn').style.display     = 'none';
    document.getElementById('useBtn').style.display        = 'none';
    document.getElementById('cameraModal').classList.add('show');
  } catch(e) { document.getElementById('imageInput').click(); }
}
function capturePhoto() {
  const v=document.getElementById('cameraPreview');
  const c=document.getElementById('cameraCanvas');
  c.width=v.videoWidth; c.height=v.videoHeight;
  c.getContext('2d').drawImage(v,0,0);
  const img=document.getElementById('capturedImg');
  img.src=c.toDataURL('image/jpeg'); img.style.display='block';
  v.style.display='none';
  document.getElementById('captureBtn').style.display='none';
  document.getElementById('retakeBtn').style.display='inline-block';
  document.getElementById('useBtn').style.display='inline-block';
}
function retakePhoto() {
  document.getElementById('cameraPreview').style.display='block';
  document.getElementById('capturedImg').style.display='none';
  document.getElementById('captureBtn').style.display='inline-block';
  document.getElementById('retakeBtn').style.display='none';
  document.getElementById('useBtn').style.display='none';
}
async function useCapture() {
  const c   = document.getElementById('cameraCanvas');
  const img = document.getElementById('capturedImg');
  closeCamera();
  await lockCameraLocation();
  c.toBlob(blob => {
    if (!blob) return;
    const file = new File([blob], 'camera_photo.jpg', { type:'image/jpeg' });
    addImageToGallery(file);
    document.getElementById('btnCamera').classList.add('done');
    const camBadge = document.getElementById('cameraBadge');
    if (camBadge) camBadge.textContent = '✓';
    document.getElementById('btnCamera').querySelector('.act-title').textContent = 'Photo Taken';
    document.getElementById('btnCamera').querySelector('.act-sub').textContent = 'Retake';
  }, 'image/jpeg', 0.85);
}
function closeCamera() {
  if (cameraStream) { cameraStream.getTracks().forEach(t=>t.stop()); cameraStream=null; }
  document.getElementById('cameraModal').classList.remove('show');
}

// ── RECORDING ──
async function toggleRecording() {
  if (isRecording) { stopRecording(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio:true });
    audioChunks=[]; recSeconds=0;
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => { if(e.data.size>0) audioChunks.push(e.data); };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t=>t.stop());
      const blob = new Blob(audioChunks, { type:'audio/webm' });
      selectedAudio = new File([blob], 'voice.webm', { type:'audio/webm' });
      const url = URL.createObjectURL(blob);
      document.getElementById('voicePlayer').src = url;
      const mins=Math.floor(recSeconds/60), secs=recSeconds%60;
      document.getElementById('voiceDuration').textContent =
        `Voice recorded (${mins}:${String(secs).padStart(2,'0')})`;
      document.getElementById('voicePreview').classList.add('show');
    };
    mediaRecorder.start();
    isRecording=true;
    recInterval = setInterval(()=>{
      recSeconds++;
      const m=Math.floor(recSeconds/60), s=recSeconds%60;
      document.getElementById('speakTimer').textContent =
        String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
    },1000);
    document.getElementById('speakBtn').classList.add('recording');
    document.getElementById('speakBtn').classList.remove('done');
    document.getElementById('speakBadge').textContent = '⏹';
    document.getElementById('speakRing').innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
    document.getElementById('speakTitle').textContent  = 'Recording';
    document.getElementById('speakSub').textContent    = 'Tap to stop';
    document.getElementById('waveform').classList.add('show');
    document.getElementById('speakTimer').style.display= 'block';
    document.getElementById('speakTimer').textContent  = '00:00';
  } catch(e) { showError('Microphone access denied.'); }
}
function stopRecording() {
  if (mediaRecorder && mediaRecorder.state!=='inactive') mediaRecorder.stop();
  clearInterval(recInterval);
  isRecording=false;
  document.getElementById('speakBtn').classList.remove('recording');
  document.getElementById('speakBtn').classList.add('done');
  document.getElementById('speakRing').innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
  document.getElementById('speakTitle').textContent = 'Recorded';
  document.getElementById('speakSub').textContent   = 'Tap to redo';
  document.getElementById('speakBadge').textContent = '✓';
  document.getElementById('waveform').classList.remove('show');
  document.getElementById('speakTimer').style.display= 'none';
}

// ── SEND REPORT → now redirects to confirm page ──
let pendingFormData = null;

async function sendReport() {
  const images = selectedImages.filter(Boolean);
  if (!images.length && !selectedVideo && !selectedAudio) {
    showError('Please add a photo or voice recording first.'); return;
  }
  document.getElementById('errorBox').style.display = 'none';

  const profile = userProfile || JSON.parse(localStorage.getItem('tampines_profile')||'null');

  // ── Resolve location string ──
  let location = '';
  if (locationSource === 'upload') {
    const addrInput = document.getElementById('uploadAddrInput');
    location = (addrInput && addrInput.value.trim()) || (profile && profile.homeAddress) || '';
  } else if (locationAddr) {
    location = locationAddr;
  } else if (userLocation) {
    location = `${userLocation.lat.toFixed(5)}, ${userLocation.lng.toFixed(5)}`;
  }

  // ── Serialize images → base64 thumbnails for sessionStorage ──
  const sendBtn = document.getElementById('sendBtn');
  if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '⏳ Preparing…'; }

  let thumbnails = [];
  try {
    thumbnails = await Promise.all(
      images.map(file => fileToDataURI(file))
    );
  } catch(e) { thumbnails = []; }

  // ── Serialize audio blob → base64 ──
  if (selectedAudio) {
    try {
      const audioB64 = await blobToBase64(selectedAudio);
      sessionStorage.setItem('tampines_pending_audio', audioB64);
    } catch(e) { sessionStorage.removeItem('tampines_pending_audio'); }
  } else {
    sessionStorage.removeItem('tampines_pending_audio');
  }

  // ── Save pending report metadata ──
  const pendingReport = {
    thumbnails,
    location,
    locationSource,
    hasAudio: !!selectedAudio,
    imageCount: images.length,
    preLabels: [],
  };
  sessionStorage.setItem('tampines_pending_report', JSON.stringify(pendingReport));

  // ── Navigate to confirmation page ──
  window.location.href = '/confirm.html';
}

// Helpers
function fileToDataURI(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = e => resolve(e.target.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = e => resolve(e.target.result.split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function setLoadingStep(n) {
  for(let i=1;i<=4;i++){
    const el=document.getElementById('ls'+i);
    if(el) el.className='ls'+(i<=n?' active':'');
  }
}

async function submitClarification(skip=false) {
  document.getElementById('clarifModal').classList.remove('show');
  const answer = skip ? '' : (document.getElementById('clarifAnswer').value.trim());
  if (pendingFormData && answer) pendingFormData.append('extra_context', answer);
  document.getElementById('loadingScreen').classList.add('show');
  setLoadingStep(3);
  try {
    const res  = await fetch('/analyze', { method:'POST', body: pendingFormData });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    showSuccess(data);
  } catch(err) {
    document.getElementById('loadingScreen').classList.remove('show');
    showError(err.message);
  }
}

// ── AGENCY CATEGORY → ICON ──
const AGENCY_ICONS = {
  cleanliness:'🗑️', structural:'🔧', electrical:'⚡',
  water:'💧', safety:'⚠️', noise:'🔊',
  pest:'🐀', vehicles:'🚗', greenery:'🌿', general:'📋'
};

// ── SUCCESS ──
function showSuccess(data) {
  const analysis = data.analysis || {};
  const routes   = data.routes   || [];

  const priority = (analysis.priority || 'LOW').toUpperCase();
  const header   = document.getElementById('successHeader');
  const icon     = document.getElementById('successIcon');
  const headline = document.getElementById('successHeadline');
  if (priority === 'CRITICAL') {
    header.style.background = '#dc2626';
    icon.textContent = '🚨';
    headline.textContent = 'CRITICAL — Call 995 Now!';
  } else if (priority === 'HIGH') {
    header.style.background = '#c2410c';
    icon.textContent = '⚠️';
    headline.textContent = 'High Priority — Agencies Notified!';
  } else {
    header.style.background = 'var(--green)';
    icon.textContent = '✅';
    headline.textContent = 'Report Sent!';
  }

  document.getElementById('successTime').textContent =
    'Submitted ' + new Date().toLocaleString('en-SG');
  document.getElementById('residentMsg').textContent =
    analysis.resident_message || 'Your report has been received. We will attend to it shortly.';

  const chip = document.getElementById('priorityVal');
  chip.textContent = priority;
  chip.className   = 'priority-chip ' + priority.toLowerCase();

  // Safety card
  const safetyCard  = document.getElementById('safetyCard');
  const safetySteps = document.getElementById('safetySteps');
  const safetyTitle = document.getElementById('safetyCardTitle');
  safetySteps.innerHTML = '';
  if (priority === 'CRITICAL' || priority === 'HIGH') {
    safetyCard.classList.add('show');
    if (priority === 'CRITICAL') {
      safetyCard.classList.add('critical-card');
      safetyTitle.textContent = '🚨 CALL 995 IMMEDIATELY — Then:';
      ['Evacuate the area immediately','Do not re-enter','Await SCDF instructions'].forEach(s => {
        const d = document.createElement('div'); d.className='safety-step'; d.textContent='• '+s; safetySteps.appendChild(d);
      });
    } else {
      safetyCard.classList.remove('critical-card');
      safetyTitle.textContent = '👉 What to Do Now';
      ['Do not touch exposed wires or wet switches','Keep children away from the area',
       'If flooding, move valuables higher','If sparks appear, call 995 immediately'].forEach(s => {
        const d = document.createElement('div'); d.className='safety-step'; d.textContent='• '+s; safetySteps.appendChild(d);
      });
    }
  } else {
    safetyCard.classList.remove('show');
  }

  // Agency list
  const agencyList = document.getElementById('agencyList');
  agencyList.innerHTML = '';
  if (routes.length > 0) {
    routes.forEach(route => {
      const cat = route.category || 'general';
      const labelsStr = (route.labels_covered||[]).map(l=>l.replace(/_/g,' ')).join(', ');
      const row = document.createElement('div');
      row.className = 'agency-row';
      row.innerHTML = `
        <div class="agency-icon-box ${cat}">${AGENCY_ICONS[cat]||'📋'}</div>
        <div style="flex:1;min-width:0;">
          <div class="agency-name">${route.agency}</div>
          <div class="agency-labels">${labelsStr}</div>
          <div class="agency-sla">⏱ Response within ${route.sla}</div>
        </div>
        <div class="agency-check">✅</div>`;
      agencyList.appendChild(row);
    });
  } else {
    agencyList.innerHTML = '<div class="agency-row"><div class="agency-name">Town Council</div></div>';
  }

  document.getElementById('caseIdVal').textContent = data.case_id || '—';

  const locCard = document.getElementById('locationCard');
  const locVal  = document.getElementById('locationVal');
  locCard.style.display = 'block';
  if (data.location) { locVal.textContent = '📍 ' + data.location; }
  else { locVal.textContent = '⚠️ Location not detected — state your block when speaking.'; locVal.style.color='var(--red)'; }

  const txCard = document.getElementById('transcriptCard');
  const txVal  = document.getElementById('transcriptVal');
  txCard.style.display = 'block';
  txVal.textContent = data.transcript ? '"' + data.transcript + '"' : 'No voice recorded.';
  if (!data.transcript) txVal.style.color = 'var(--muted)';

  const waCard = document.getElementById('whatsappCard');
  const waVal  = document.getElementById('whatsappVal');
  if (userProfile && userProfile.phone) {
    waCard.style.display = 'block';
    const waOk = data.dispatch && data.dispatch.whatsapp_sent;
    if (waOk) {
      waVal.textContent = '✅ WhatsApp confirmation sent to ' + userProfile.phone;
      waVal.style.color = '';
    } else if (!data.dispatch) {
      waVal.textContent = '⚠️ WhatsApp not sent — no report to confirm.';
      waVal.style.color = 'var(--red)';
    } else {
      waVal.style.color = 'var(--red)';
      waVal.innerHTML =
        '❌ WhatsApp delivery failed for ' + userProfile.phone +
        '.<br><small>Check that your number joined the Twilio sandbox ' +
        'by sending <b>join &lt;sandbox-word&gt;</b> to +1 415 523 8886, ' +
        'or verify TWILIO_FROM_PHONE in your .env.</small>';
    }
  } else { waCard.style.display = 'none'; }

  // ── Save to history ──
  if (typeof window.saveToHistory === 'function') {
    const labelsSummary = (analysis.final_labels || [])
      .map(l => l.replace(/_/g, ' ')).join(', ');
    const summaryText = analysis.case_summary
      || analysis.resident_message
      || (labelsSummary ? 'Issues reported: ' + labelsSummary : null)
      || 'Report submitted';

    const histEntry = {
      caseId:     data.case_id || '—',
      priority:   (analysis.priority || 'LOW').toUpperCase(),
      summary:    summaryText,
      agencies:   (data.routes || []).map(r => r.agency).join(', '),
      location:   data.location || locationAddr || '',
      transcript: data.transcript || '',
      date:       new Date().toLocaleString('en-SG'),
      thumbnail:  null
    };

    const firstImg = (selectedImages || []).find(Boolean);
    if (firstImg) {
      const reader = new FileReader();
      reader.onload = function(e) {
        const imgEl = new Image();
        imgEl.onload = function() {
          const MAX = 1200;
          const scale = Math.min(1, MAX / Math.max(imgEl.width, imgEl.height));
          const canvas = document.createElement('canvas');
          canvas.width  = Math.round(imgEl.width  * scale);
          canvas.height = Math.round(imgEl.height * scale);
          canvas.getContext('2d').drawImage(imgEl, 0, 0, canvas.width, canvas.height);
          histEntry.thumbnail = canvas.toDataURL('image/jpeg', 0.92);
          window.saveToHistory(histEntry);
        };
        imgEl.src = e.target.result;
      };
      reader.readAsDataURL(firstImg);
    } else {
      window.saveToHistory(histEntry);
    }
  }

  document.getElementById('loadingScreen').classList.remove('show');
  document.getElementById('successScreen').classList.add('show');
}

// ── RESET ──
function resetApp() {
  selectedImages=[]; selectedAudio=null; selectedVideo=null;
  pendingFormData = null;
  locationSource = null;
  document.getElementById('uploadAddrStrip').style.display = 'none';
  document.getElementById('uploadAddrInput').value = '';
  if(isRecording) stopRecording();
  clearAllMedia();

  const sb = document.getElementById('speakBtn');
  sb.className = 'act-btn act-speak';
  document.getElementById('speakRing').innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>';
  document.getElementById('speakTitle').textContent    = 'Speak';
  document.getElementById('speakSub').textContent      = 'Voice report';
  document.getElementById('speakBadge').textContent    = 'Rec';
  const cb = document.getElementById('btnCamera');
  cb.classList.remove('done');
  const camBadgeR = document.getElementById('cameraBadge');
  if (camBadgeR) camBadgeR.textContent = 'Snap';
  cb.querySelector('.act-title').textContent = 'Take Photo';
  cb.querySelector('.act-sub').textContent   = 'Camera';
  const ub = document.getElementById('btnUpload');
  ub.classList.remove('done');
  const upBadgeR = document.getElementById('uploadBadge');
  if (upBadgeR) upBadgeR.textContent = 'Gallery';
  ub.querySelector('.act-title').textContent = 'Upload Photo';
  ub.querySelector('.act-sub').textContent   = 'Pick from your gallery';
  document.getElementById('waveform').classList.remove('show');
  document.getElementById('speakTimer').style.display  = 'none';
  document.getElementById('voicePreview').classList.remove('show');
  document.getElementById('voicePlayer').src           = '';

  document.getElementById('successScreen').classList.remove('show');
  document.getElementById('successHeader').style.background = '';
  document.getElementById('locationCard').style.display   = 'none';
  document.getElementById('transcriptCard').style.display = 'none';
  document.getElementById('whatsappCard').style.display   = 'none';
  document.getElementById('locationVal').style.color      = '';
  document.getElementById('transcriptVal').style.color    = '';
  document.getElementById('safetyCard').classList.remove('show','critical-card');
  document.getElementById('agencyList').innerHTML         = '';

  startGPS();
}

// ── ERROR ──
function showError(msg) {
  const box = document.getElementById('errorBox');
  if (!box) return;
  box.textContent = '⚠️ ' + msg;
  box.style.display = 'block';
  setTimeout(() => { box.style.display = 'none'; }, 6000);
}
// ── Show success if returning from confirm page ──
(function checkReturnSuccess() {
  const raw = sessionStorage.getItem('tampines_success');
  if (!raw) return;
  sessionStorage.removeItem('tampines_success');
  try {
    const data = JSON.parse(raw);
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => showSuccess(data));
    } else {
      setTimeout(() => showSuccess(data), 100);
    }
  } catch(e) {}
})();