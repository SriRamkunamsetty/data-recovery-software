/**
 * RecoverX Product Landing Page Scripts
 * Interactive canvas background, live scanner simulator, gallery carousel & download trigger.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Animated Particle Network Canvas
  initBackgroundCanvas();

  // 2. Theme Toggle (Dark / Light)
  initThemeToggle();

  // 3. Live Sector Scanner Simulator
  initSimulator();

  // 4. Screenshots Gallery Carousel
  initGallery();

  // 5. Download Triggers & Toast Modal
  initDownloadHandlers();
});

/* -------------------------------------------------------------
 * 1. Background Particle Network Canvas
 * ------------------------------------------------------------- */
function initBackgroundCanvas() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let width = (canvas.width = window.innerWidth);
  let height = (canvas.height = window.innerHeight);

  window.addEventListener('resize', () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });

  const particles = [];
  const particleCount = Math.min(Math.floor((width * height) / 18000), 75);

  for (let i = 0; i < particleCount; i++) {
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.45,
      vy: (Math.random() - 0.5) * 0.45,
      radius: Math.random() * 1.8 + 0.8,
    });
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);

    // Draw connecting lines
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 130) {
          ctx.beginPath();
          const opacity = (1 - dist / 130) * 0.15;
          ctx.strokeStyle = `rgba(56, 189, 248, ${opacity})`;
          ctx.lineWidth = 0.8;
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    // Draw particle nodes
    for (const p of particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(59, 130, 246, 0.45)';
      ctx.fill();

      p.x += p.vx;
      p.y += p.vy;

      if (p.x < 0 || p.x > width) p.vx *= -1;
      if (p.y < 0 || p.y > height) p.vy *= -1;
    }

    requestAnimationFrame(draw);
  }

  draw();
}

/* -------------------------------------------------------------
 * 2. Theme Toggle
 * ------------------------------------------------------------- */
function initThemeToggle() {
  const toggleBtn = document.getElementById('theme-toggle');
  const htmlEl = document.documentElement;

  toggleBtn.addEventListener('click', () => {
    const currentTheme = htmlEl.getAttribute('data-theme') || 'dark';
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
    htmlEl.setAttribute('data-theme', nextTheme);
  });
}

/* -------------------------------------------------------------
 * 3. Live Sector Scanner Simulator
 * ------------------------------------------------------------- */
function initSimulator() {
  const startBtn = document.getElementById('sim-start-btn');
  const resetBtn = document.getElementById('sim-reset-btn');
  const radialBar = document.getElementById('sim-radial-bar');
  const percentText = document.getElementById('sim-percent-text');
  const statusLabel = document.getElementById('sim-status-label');
  const speedText = document.getElementById('sim-speed');
  const offsetText = document.getElementById('sim-offset');
  const filesText = document.getElementById('sim-files');
  const badText = document.getElementById('sim-bad');
  const candidateBody = document.getElementById('sim-candidate-body');
  const candCount = document.getElementById('cand-count');
  const consoleBox = document.getElementById('sim-console');

  const circumference = 2 * Math.PI * 82; // ~515.22
  let scanInterval = null;
  let progress = 0;
  let isScanning = false;

  const mockFiles = [
    { name: 'DCIM_0042.JPG', size: '2.4 MB', method: 'FAT32 Metadata', status: 'Verified (Valid JFIF)', color: 'text-emerald' },
    { name: 'Financial_Q3.PDF', size: '840 KB', method: 'Signature Carver', status: 'Verified (%PDF-1.7)', color: 'text-emerald' },
    { name: 'Family_Video.MOV', size: '48.1 MB', method: 'Direct Stream', status: 'Integrity Clean', color: 'text-emerald' },
    { name: 'Database_Backup.ZIP', size: '12.8 MB', method: 'Signature Carver', status: 'Verified (PK0304)', color: 'text-emerald' },
    { name: 'Notes_Corrupt.txt', size: '14 KB', method: 'Allocation Table', status: 'Marked Overwritten', color: 'text-amber' },
  ];

  function log(msg) {
    const line = document.createElement('div');
    line.className = 'log-line';
    const time = new Date().toISOString().substring(11, 19);
    line.textContent = `[${time}] ${msg}`;
    consoleBox.appendChild(line);
    consoleBox.scrollTop = consoleBox.scrollHeight;
  }

  startBtn.addEventListener('click', () => {
    if (isScanning) return;
    isScanning = true;
    startBtn.disabled = true;
    statusLabel.textContent = 'SCANNING...';
    candidateBody.innerHTML = '';
    candCount.textContent = '0';
    log('Initiating sector sweep across 65,536 clusters (Direct IOCTL)...');

    let foundIdx = 0;
    progress = 0;

    scanInterval = setInterval(() => {
      progress += 1.5;
      if (progress > 100) progress = 100;

      // Update radial stroke
      const offset = circumference - (progress / 100) * circumference;
      radialBar.style.strokeDashoffset = offset;
      percentText.textContent = `${Math.floor(progress)}%`;

      // Telemetry metrics
      const currentSector = Math.floor((progress / 100) * 62500000);
      offsetText.textContent = `0x${(currentSector * 512).toString(16).toUpperCase().padStart(8, '0')}`;
      speedText.textContent = `${(45 + Math.random() * 12).toFixed(1)} MB/s`;

      if (progress >= 20 && foundIdx === 0) {
        addMockCandidate(mockFiles[0]);
        foundIdx++;
        log('Magic signature match: JPEG JFIF header at cluster 4096 (DCIM_0042.JPG)');
      }
      if (progress >= 45 && foundIdx === 1) {
        addMockCandidate(mockFiles[1]);
        foundIdx++;
        log('Signature match: PDF document structure trailer EOF (Financial_Q3.PDF)');
      }
      if (progress >= 65 && foundIdx === 2) {
        badText.textContent = '1';
        log('WARNING: CRC error detected on LBA 48828125. Auto-retry triggered (attempt 2/3: OK)');
        addMockCandidate(mockFiles[2]);
        foundIdx++;
      }
      if (progress >= 82 && foundIdx === 3) {
        addMockCandidate(mockFiles[3]);
        foundIdx++;
        log('Central directory validated: ZIP container intact (Database_Backup.ZIP)');
      }
      if (progress >= 95 && foundIdx === 4) {
        addMockCandidate(mockFiles[4]);
        foundIdx++;
      }

      if (progress >= 100) {
        clearInterval(scanInterval);
        isScanning = false;
        startBtn.disabled = false;
        statusLabel.textContent = 'COMPLETED';
        log('Scan complete: 5 candidates identified. Integrity hashes verified (SHA-256).');
      }
    }, 80);
  });

  resetBtn.addEventListener('click', () => {
    if (scanInterval) clearInterval(scanInterval);
    isScanning = false;
    startBtn.disabled = false;
    progress = 0;
    radialBar.style.strokeDashoffset = circumference;
    percentText.textContent = '0%';
    statusLabel.textContent = 'IDLE';
    speedText.textContent = '0.0 MB/s';
    offsetText.textContent = '0x00000000';
    filesText.textContent = '0';
    badText.textContent = '0';
    candCount.textContent = '0';
    candidateBody.innerHTML = '<tr class="empty-row"><td colspan="4">Click "Start Simulated Cluster Scan" to initiate forensic discovery.</td></tr>';
    consoleBox.innerHTML = '<div class="log-line">[SYSTEM] Ready for direct physical block streaming.</div>';
  });

  function addMockCandidate(item) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${item.name}</strong></td>
      <td>${item.size}</td>
      <td>${item.method}</td>
      <td><span class="${item.color}">${item.status}</span></td>
    `;
    candidateBody.appendChild(tr);
    filesText.textContent = candidateBody.children.length;
    candCount.textContent = candidateBody.children.length;
  }

  // Tabs for simulator
  const simTabs = document.querySelectorAll('.sim-tab');
  simTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      simTabs.forEach((t) => t.classList.remove('active'));
      document.querySelectorAll('.sim-tab-content').forEach((c) => c.classList.remove('active'));
      tab.classList.add('active');
      const target = tab.getAttribute('data-tab');
      document.getElementById(`tab-${target}`).classList.add('active');
    });
  });
}

/* -------------------------------------------------------------
 * 4. Screenshots Gallery Carousel
 * ------------------------------------------------------------- */
function initGallery() {
  const tabBtns = document.querySelectorAll('.gallery-tab-btn');
  const mainImg = document.getElementById('gallery-main-img');

  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      tabBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const imgName = btn.getAttribute('data-img');

      mainImg.style.opacity = '0.2';
      setTimeout(() => {
        mainImg.src = `assets/${imgName}`;
        mainImg.style.opacity = '1';
      }, 150);
    });
  });
}

/* -------------------------------------------------------------
 * 5. Download Triggers & Toast Modal
 * ------------------------------------------------------------- */
function initDownloadHandlers() {
  const toast = document.getElementById('download-toast');
  const closeBtn = document.getElementById('toast-close-btn');
  const downloadBtns = [
    document.getElementById('main-download-btn'),
    document.getElementById('hero-download-trigger'),
  ];

  function showToast() {
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
    }, 9000);
  }

  downloadBtns.forEach((btn) => {
    if (btn) {
      btn.addEventListener('click', () => {
        showToast();
      });
    }
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      toast.classList.remove('show');
    });
  }
}
