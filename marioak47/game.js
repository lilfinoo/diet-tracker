(() => {
  "use strict";

  const canvas = document.querySelector("#game");
  const ctx = canvas.getContext("2d");
  const startScreen = document.querySelector("#start-screen");
  const messageScreen = document.querySelector("#message-screen");
  const startButton = document.querySelector("#start-button");
  const restartButton = document.querySelector("#restart-button");
  const pauseButton = document.querySelector("#pause-button");
  const resultKicker = document.querySelector("#result-kicker");
  const resultTitle = document.querySelector("#result-title");
  const resultCopy = document.querySelector("#result-copy");

  const WIDTH = canvas.width;
  const HEIGHT = canvas.height;
  const LEVEL_WIDTH = 8400;
  const GRAVITY = 2200;
  const GROUND_Y = 600;
  const PSI_MAX = 20;

  ctx.imageSmoothingEnabled = false;

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const approach = (value, target, amount) =>
    value < target ? Math.min(value + amount, target) : Math.max(value - amount, target);
  const overlap = (a, b) =>
    a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  const seededNoise = (n) => {
    const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
  };

  const input = {
    left: false,
    right: false,
    jump: false,
    shoot: false,
    jumpQueued: false,
  };

  let state = "menu";
  let elapsed = 0;
  let remainingTime = 180;
  let cameraX = 0;
  let screenShake = 0;
  let score = 0;
  let kills = 0;
  let audioContext = null;
  let lastFrame = performance.now();
  let player;
  let enemies = [];
  let bullets = [];
  let particles = [];

  const solids = [
    { x: -300, y: GROUND_Y, w: 1630, h: 180, type: "ground" },
    { x: 1470, y: GROUND_Y, w: 1190, h: 180, type: "ground" },
    { x: 2820, y: GROUND_Y, w: 1570, h: 180, type: "ground" },
    { x: 4550, y: GROUND_Y, w: 1410, h: 180, type: "ground" },
    { x: 6120, y: GROUND_Y, w: 2580, h: 180, type: "ground" },

    { x: 560, y: 475, w: 168, h: 34, type: "brick" },
    { x: 810, y: 390, w: 54, h: 54, type: "crate" },
    { x: 1030, y: 512, w: 90, h: 88, type: "pipe" },
    { x: 1650, y: 470, w: 230, h: 34, type: "brick" },
    { x: 1980, y: 510, w: 94, h: 90, type: "pipe" },
    { x: 2200, y: 400, w: 210, h: 34, type: "brick" },
    { x: 2430, y: 330, w: 54, h: 54, type: "crate" },
    { x: 3000, y: 490, w: 180, h: 34, type: "brick" },
    { x: 3330, y: 505, w: 98, h: 95, type: "pipe" },
    { x: 3590, y: 420, w: 260, h: 34, type: "brick" },
    { x: 3970, y: 345, w: 54, h: 54, type: "crate" },
    { x: 4700, y: 470, w: 150, h: 34, type: "brick" },
    { x: 5000, y: 395, w: 225, h: 34, type: "brick" },
    { x: 5430, y: 500, w: 104, h: 100, type: "pipe" },
    { x: 5680, y: 350, w: 170, h: 34, type: "brick" },
    { x: 6300, y: 500, w: 98, h: 100, type: "pipe" },
    { x: 6570, y: 445, w: 240, h: 34, type: "brick" },
    { x: 7000, y: 365, w: 230, h: 34, type: "brick" },
    { x: 7390, y: 480, w: 170, h: 34, type: "brick" },
    { x: 7720, y: 520, w: 84, h: 80, type: "pipe" },
  ];

  const decorations = [
    { x: 260, text: "ROTA 01 →", tone: "red" },
    { x: 1550, text: "GRAMA ALTA", tone: "cream" },
    { x: 2880, text: "ÁREA PSI", tone: "red" },
    { x: 4600, text: "ROTA 02", tone: "cream" },
    { x: 6200, text: "LAB →", tone: "red" },
  ];

  const enemySpawns = [
    [760, 520, 530, 980],
    [1190, 520, 980, 1280],
    [1570, 520, 1500, 1910],
    [1840, 520, 1500, 1930],
    [2260, 320, 2200, 2390],
    [2510, 520, 2090, 2600],
    [2910, 520, 2850, 3290],
    [3190, 520, 2850, 3290],
    [3670, 340, 3590, 3800],
    [4110, 520, 3450, 4340],
    [4650, 520, 4580, 4940],
    [5150, 315, 5000, 5170],
    [5310, 520, 5250, 5400],
    [5740, 270, 5680, 5800],
    [6190, 520, 6140, 6280],
    [6700, 365, 6570, 6750],
    [6920, 520, 6420, 7350],
    [7150, 285, 7000, 7170],
    [7510, 400, 7390, 7500],
    [7860, 520, 7820, 8080],
    [8000, 520, 7820, 8120],
  ];

  function resetGame() {
    input.left = false;
    input.right = false;
    input.jump = false;
    input.shoot = false;
    input.jumpQueued = false;
    player = {
      x: 150,
      y: 490,
      w: 46,
      h: 66,
      vx: 0,
      vy: 0,
      facing: 1,
      grounded: false,
      coyote: 0,
      hp: 3,
      ammo: PSI_MAX,
      reloading: 0,
      fireCooldown: 0,
      invulnerable: 0,
      muzzle: 0,
      walkCycle: 0,
    };
    enemies = enemySpawns.map(([x, y, minX, maxX], index) => ({
      x,
      y,
      w: index % 7 === 6 ? 58 : 50,
      h: index % 7 === 6 ? 58 : 50,
      vx: index % 2 ? -48 : 48,
      vy: 0,
      minX,
      maxX,
      hp: index % 7 === 6 ? 2 : 1,
      grounded: false,
      alive: true,
      hit: 0,
      phase: index * 0.7,
      kind: index % 4,
    }));
    bullets = [];
    particles = [];
    elapsed = 0;
    remainingTime = 180;
    cameraX = 0;
    score = 0;
    kills = 0;
    screenShake = 0;
  }

  function beginGame() {
    ensureAudio();
    resetGame();
    state = "running";
    startScreen.classList.remove("is-visible");
    messageScreen.classList.remove("is-visible");
    playTone(220, 0.08, "square", 0.05);
    window.setTimeout(() => playTone(330, 0.1, "square", 0.04), 70);
  }

  function ensureAudio() {
    if (!audioContext) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) audioContext = new AudioContext();
    }
    if (audioContext?.state === "suspended") audioContext.resume();
  }

  function playTone(frequency, duration, type = "square", volume = 0.025, slide = 0) {
    if (!audioContext || audioContext.state !== "running") return;
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, audioContext.currentTime);
    if (slide) {
      oscillator.frequency.exponentialRampToValueAtTime(
        Math.max(35, frequency + slide),
        audioContext.currentTime + duration,
      );
    }
    gain.gain.setValueAtTime(volume, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + duration);
    oscillator.connect(gain).connect(audioContext.destination);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + duration);
  }

  function moveAndCollide(body, dx, dy) {
    body.x += dx;
    for (const solid of solids) {
      if (!overlap(body, solid)) continue;
      if (dx > 0) body.x = solid.x - body.w;
      if (dx < 0) body.x = solid.x + solid.w;
      body.vx = 0;
    }

    body.y += dy;
    body.grounded = false;
    for (const solid of solids) {
      if (!overlap(body, solid)) continue;
      if (dy > 0) {
        body.y = solid.y - body.h;
        body.vy = 0;
        body.grounded = true;
      }
      if (dy < 0) {
        body.y = solid.y + solid.h;
        body.vy = 0;
      }
    }
  }

  function pointInSolid(x, y) {
    return solids.some((solid) => x >= solid.x && x <= solid.x + solid.w && y >= solid.y && y <= solid.y + solid.h);
  }

  function updatePlayer(dt) {
    const targetVx = (input.right ? 1 : 0) - (input.left ? 1 : 0);
    if (targetVx) {
      player.vx = approach(player.vx, targetVx * 300, (player.grounded ? 1800 : 900) * dt);
      player.facing = targetVx;
    } else {
      player.vx = approach(player.vx, 0, (player.grounded ? 2200 : 500) * dt);
    }

    player.coyote = player.grounded ? 0.11 : Math.max(0, player.coyote - dt);
    if (input.jumpQueued && player.coyote > 0) {
      player.vy = -760;
      player.grounded = false;
      player.coyote = 0;
      input.jumpQueued = false;
      spawnDust(player.x + player.w / 2, player.y + player.h, 5);
      playTone(260, 0.12, "square", 0.025, 170);
    }
    if (!input.jump && player.vy < -270) player.vy += 1500 * dt;

    player.vy += GRAVITY * dt;
    moveAndCollide(player, player.vx * dt, player.vy * dt);
    player.x = clamp(player.x, 0, LEVEL_WIDTH - player.w);
    player.walkCycle += Math.abs(player.vx) * dt * 0.045;
    player.fireCooldown = Math.max(0, player.fireCooldown - dt);
    player.invulnerable = Math.max(0, player.invulnerable - dt);
    player.muzzle = Math.max(0, player.muzzle - dt);

    if (player.reloading > 0) {
      player.reloading -= dt;
      if (player.reloading <= 0) {
        player.ammo = PSI_MAX;
        playTone(680, 0.12, "sine", 0.035, 180);
      }
    } else if (input.shoot && player.fireCooldown <= 0) {
      shoot();
    }

    if (player.y > HEIGHT + 180) loseGame("Mewtwo caiu no abismo antes de alcançar o laboratório.");
    if (player.x > 8150) winGame();
  }

  function shoot() {
    if (player.ammo <= 0) {
      startReload();
      return;
    }
    const direction = player.facing;
    bullets.push({
      x: player.x + player.w / 2 + direction * 34 - 11,
      y: player.y + 18,
      w: 22,
      h: 22,
      vx: direction * 920,
      life: 0.9,
    });
    spawnPsychicPulse(player.x + player.w / 2 + direction * 28, player.y + 25, 5);
    player.ammo -= 1;
    player.fireCooldown = 0.16;
    player.muzzle = 0.1;
    screenShake = Math.max(screenShake, 3);
    playTone(520, 0.12, "sine", 0.035, 300);
    if (player.ammo === 0) window.setTimeout(startReload, 160);
  }

  function startReload() {
    if (state !== "running" || player.reloading > 0 || player.ammo === PSI_MAX) return;
    player.reloading = 1.15;
    playTone(350, 0.14, "sine", 0.025, 220);
  }

  function updateEnemies(dt) {
    for (const enemy of enemies) {
      if (!enemy.alive) continue;
      enemy.hit = Math.max(0, enemy.hit - dt);
      enemy.phase += dt * 5;

      if (enemy.x <= enemy.minX) enemy.vx = Math.abs(enemy.vx);
      if (enemy.x + enemy.w >= enemy.maxX) enemy.vx = -Math.abs(enemy.vx);
      const aheadX = enemy.vx > 0 ? enemy.x + enemy.w + 8 : enemy.x - 8;
      if (enemy.grounded && !pointInSolid(aheadX, enemy.y + enemy.h + 8)) enemy.vx *= -1;

      enemy.vy += GRAVITY * dt;
      moveAndCollide(enemy, enemy.vx * dt, enemy.vy * dt);

      if (overlap(player, enemy) && player.invulnerable <= 0) {
        if (player.vy > 180 && player.y + player.h < enemy.y + enemy.h * 0.65) {
          damageEnemy(enemy, 2);
          player.vy = -470;
          playTone(120, 0.08, "square", 0.035, -50);
        } else {
          damagePlayer(enemy.x + enemy.w / 2);
        }
      }
    }
  }

  function damageEnemy(enemy, damage) {
    if (!enemy.alive) return;
    enemy.hp -= damage;
    enemy.hit = 0.08;
    if (enemy.hp <= 0) {
      enemy.alive = false;
      kills += 1;
      score += 500;
      const burstColors = ["#f2cb3f", "#55a98c", "#e8833f", "#e7a5c7"];
      spawnBurst(enemy.x + enemy.w / 2, enemy.y + enemy.h / 2, burstColors[enemy.kind], 14);
      playTone(240, 0.12, "sine", 0.04, -110);
    }
  }

  function damagePlayer(sourceX) {
    player.hp -= 1;
    player.invulnerable = 1.5;
    player.vx = player.x < sourceX ? -380 : 380;
    player.vy = -430;
    screenShake = 14;
    spawnBurst(player.x + player.w / 2, player.y + 30, "#f2d056", 10);
    playTone(115, 0.28, "sawtooth", 0.05, -70);
    if (player.hp <= 0) loseGame("Mewtwo ficou sem energia para continuar.");
  }

  function updateBullets(dt) {
    for (let i = bullets.length - 1; i >= 0; i -= 1) {
      const bullet = bullets[i];
      bullet.x += bullet.vx * dt;
      bullet.life -= dt;
      let removed = bullet.life <= 0;

      if (!removed && solids.some((solid) => overlap(bullet, solid))) {
        spawnSparks(bullet.x, bullet.y, 5);
        removed = true;
      }

      if (!removed) {
        for (const enemy of enemies) {
          if (!enemy.alive || !overlap(bullet, enemy)) continue;
          damageEnemy(enemy, 1);
          spawnSparks(bullet.x, bullet.y, 7);
          removed = true;
          break;
        }
      }

      if (removed) bullets.splice(i, 1);
    }
  }

  function spawnSparks(x, y, count) {
    for (let i = 0; i < count; i += 1) {
      particles.push({
        x,
        y,
        vx: (Math.random() - 0.5) * 360,
        vy: -80 - Math.random() * 260,
        life: 0.25 + Math.random() * 0.2,
        maxLife: 0.45,
        size: 2 + Math.random() * 4,
        color: i % 2 ? "#fff1a1" : "#f08932",
      });
    }
  }

  function spawnPsychicPulse(x, y, count) {
    for (let i = 0; i < count; i += 1) {
      const angle = (Math.PI * 2 * i) / count;
      particles.push({
        x,
        y,
        vx: Math.cos(angle) * 120,
        vy: Math.sin(angle) * 120,
        life: 0.28,
        maxLife: 0.28,
        size: 5 + (i % 2) * 3,
        color: i % 2 ? "#f3a8ff" : "#9a79ff",
      });
    }
  }

  function spawnDust(x, y, count) {
    for (let i = 0; i < count; i += 1) {
      particles.push({
        x: x + (Math.random() - 0.5) * 28,
        y,
        vx: (Math.random() - 0.5) * 120,
        vy: -30 - Math.random() * 90,
        life: 0.35 + Math.random() * 0.25,
        maxLife: 0.6,
        size: 5 + Math.random() * 7,
        color: "#e7ddba",
      });
    }
  }

  function spawnBurst(x, y, color, count) {
    for (let i = 0; i < count; i += 1) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 80 + Math.random() * 310;
      particles.push({
        x,
        y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 120,
        life: 0.45 + Math.random() * 0.45,
        maxLife: 0.9,
        size: 4 + Math.random() * 8,
        color,
      });
    }
  }

  function updateEffects(dt) {
    for (let i = particles.length - 1; i >= 0; i -= 1) {
      const particle = particles[i];
      particle.vy += 750 * dt;
      particle.x += particle.vx * dt;
      particle.y += particle.vy * dt;
      particle.life -= dt;
      if (particle.life <= 0) particles.splice(i, 1);
    }
  }

  function update(dt) {
    elapsed += dt;
    remainingTime -= dt;
    if (remainingTime <= 0) {
      remainingTime = 0;
      loseGame("O tempo da batalha acabou.");
      return;
    }

    updatePlayer(dt);
    if (state !== "running") return;
    updateEnemies(dt);
    updateBullets(dt);
    updateEffects(dt);

    const lookAhead = player.facing * 105 + player.vx * 0.28;
    const targetCamera = clamp(player.x - WIDTH * 0.38 + lookAhead, 0, LEVEL_WIDTH - WIDTH);
    cameraX += (targetCamera - cameraX) * Math.min(1, dt * 4.5);
    screenShake = Math.max(0, screenShake - dt * 34);
  }

  function winGame() {
    if (state !== "running") return;
    state = "won";
    const timeBonus = Math.floor(remainingTime) * 50;
    score += timeBonus;
    resultKicker.textContent = "BATALHA CONCLUÍDA";
    resultTitle.textContent = "LABORATÓRIO LIVRE";
    resultCopy.textContent = `${kills}/${enemySpawns.length} Pokémon derrotados · ${String(score).padStart(6, "0")} pontos`;
    messageScreen.classList.add("is-visible");
    playTone(330, 0.12, "square", 0.04);
    window.setTimeout(() => playTone(440, 0.16, "square", 0.04), 120);
    window.setTimeout(() => playTone(660, 0.28, "square", 0.04), 260);
  }

  function loseGame(reason) {
    if (state !== "running") return;
    state = "lost";
    resultKicker.textContent = "BATALHA ENCERRADA";
    resultTitle.textContent = "FORA DE COMBATE";
    resultCopy.textContent = `${reason} Placar: ${String(score).padStart(6, "0")}.`;
    messageScreen.classList.add("is-visible");
  }

  function togglePause() {
    if (state === "running") {
      state = "paused";
      pauseButton.textContent = "▶";
    } else if (state === "paused") {
      state = "running";
      pauseButton.textContent = "Ⅱ";
      lastFrame = performance.now();
    }
  }

  function drawBackground() {
    const sky = ctx.createLinearGradient(0, 0, 0, HEIGHT);
    sky.addColorStop(0, "#6c5ba0");
    sky.addColorStop(0.58, "#a88fc2");
    sky.addColorStop(1, "#ebc8c6");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    ctx.fillStyle = "rgba(255, 245, 204, 0.7)";
    ctx.beginPath();
    ctx.arc(1010, 130, 68, 0, Math.PI * 2);
    ctx.fill();

    drawCloud(((180 - cameraX * 0.08) % 1500 + 1500) % 1500 - 120, 120, 1.15);
    drawCloud(((790 - cameraX * 0.05) % 1650 + 1650) % 1650 - 160, 205, 0.8);
    drawCloud(((1280 - cameraX * 0.1) % 1700 + 1700) % 1700 - 100, 80, 0.65);

    ctx.fillStyle = "#776c91";
    ctx.beginPath();
    ctx.moveTo(0, 520);
    for (let x = -100; x <= WIDTH + 150; x += 170) {
      const worldX = x + cameraX * 0.18;
      const peak = 315 + seededNoise(Math.floor(worldX / 170)) * 70;
      ctx.quadraticCurveTo(x + 85, peak, x + 170, 520);
    }
    ctx.lineTo(WIDTH, HEIGHT);
    ctx.lineTo(0, HEIGHT);
    ctx.fill();

    ctx.fillStyle = "#535a76";
    ctx.beginPath();
    ctx.moveTo(0, 560);
    for (let x = -140; x <= WIDTH + 200; x += 210) {
      const peak = 400 + seededNoise(Math.floor((x + cameraX * 0.33) / 210)) * 55;
      ctx.quadraticCurveTo(x + 105, peak, x + 210, 560);
    }
    ctx.lineTo(WIDTH, HEIGHT);
    ctx.lineTo(0, HEIGHT);
    ctx.fill();

    const treeOffset = -(cameraX * 0.47) % 260;
    for (let x = treeOffset - 100; x < WIDTH + 120; x += 260) drawTree(x, 430, 0.8);
  }

  function drawCloud(x, y, scale) {
    ctx.fillStyle = "rgba(246, 242, 211, 0.82)";
    ctx.fillRect(x, y, 180 * scale, 30 * scale);
    ctx.beginPath();
    ctx.arc(x + 45 * scale, y, 36 * scale, Math.PI, 0);
    ctx.arc(x + 95 * scale, y - 16 * scale, 48 * scale, Math.PI, 0);
    ctx.arc(x + 145 * scale, y, 31 * scale, Math.PI, 0);
    ctx.fill();
  }

  function drawTree(x, y, scale) {
    ctx.fillStyle = "#4a3e2b";
    ctx.fillRect(x + 44 * scale, y, 24 * scale, 150 * scale);
    ctx.fillStyle = "#335d3d";
    ctx.fillRect(x, y - 35 * scale, 110 * scale, 58 * scale);
    ctx.fillStyle = "#47764c";
    ctx.fillRect(x + 17 * scale, y - 70 * scale, 78 * scale, 50 * scale);
    ctx.fillStyle = "#6f955c";
    ctx.fillRect(x + 28 * scale, y - 60 * scale, 22 * scale, 16 * scale);
  }

  function drawWorld() {
    const shakeX = screenShake ? (Math.random() - 0.5) * screenShake : 0;
    const shakeY = screenShake ? (Math.random() - 0.5) * screenShake * 0.55 : 0;
    ctx.save();
    ctx.translate(Math.round(-cameraX + shakeX), Math.round(shakeY));

    drawDecorations();
    for (const solid of solids) drawSolid(solid);
    drawGoal();

    for (const enemy of enemies) if (enemy.alive) drawEnemy(enemy);
    for (const bullet of bullets) drawBullet(bullet);
    drawPlayer();
    for (const particle of particles) drawParticle(particle);

    ctx.restore();
  }

  function drawDecorations() {
    for (const sign of decorations) {
      ctx.fillStyle = "#4f3c28";
      ctx.fillRect(sign.x + 50, 535, 12, 65);
      ctx.fillStyle = sign.tone === "red" ? "#7652b5" : "#dfd3e8";
      ctx.fillRect(sign.x, 500, 112, 45);
      ctx.strokeStyle = "#29261d";
      ctx.lineWidth = 5;
      ctx.strokeRect(sign.x, 500, 112, 45);
      ctx.fillStyle = sign.tone === "red" ? "#fbebff" : "#29213b";
      ctx.font = "bold 12px 'Roboto Mono', monospace";
      ctx.textAlign = "center";
      ctx.fillText(sign.text, sign.x + 56, 528);
    }

    for (let x = 0; x < LEVEL_WIDTH; x += 360) {
      if (seededNoise(x) > 0.38) {
        ctx.fillStyle = "#42673b";
        ctx.fillRect(x + 90, 576, 7, 24);
        ctx.fillRect(x + 105, 566, 7, 34);
        ctx.fillStyle = "#efcf4e";
        ctx.fillRect(x + 101, 558, 14, 14);
      }
    }
  }

  function drawSolid(solid) {
    if (solid.type === "ground") {
      ctx.fillStyle = "#273b29";
      ctx.fillRect(solid.x, solid.y, solid.w, solid.h);
      ctx.fillStyle = "#739348";
      ctx.fillRect(solid.x, solid.y, solid.w, 18);
      ctx.fillStyle = "#a4ba5e";
      ctx.fillRect(solid.x, solid.y, solid.w, 6);
      ctx.fillStyle = "#3f5335";
      for (let x = solid.x + 14; x < solid.x + solid.w; x += 48) {
        ctx.fillRect(x, solid.y + 38 + ((x / 48) % 2) * 18, 22, 16);
      }
      ctx.fillStyle = "#1d2b22";
      for (let x = solid.x + 30; x < solid.x + solid.w; x += 72) {
        ctx.fillRect(x, solid.y + 98 + ((x / 72) % 2) * 16, 28, 20);
      }
      return;
    }

    if (solid.type === "pipe") {
      ctx.fillStyle = "#1b321f";
      ctx.fillRect(solid.x + 10, solid.y + 16, solid.w - 20, solid.h - 16);
      ctx.fillStyle = "#47794c";
      ctx.fillRect(solid.x + 19, solid.y + 16, 19, solid.h - 16);
      ctx.fillStyle = "#162719";
      ctx.fillRect(solid.x + solid.w - 29, solid.y + 16, 18, solid.h - 16);
      ctx.fillStyle = "#568c55";
      ctx.fillRect(solid.x, solid.y, solid.w, 25);
      ctx.fillStyle = "#8aad60";
      ctx.fillRect(solid.x + 9, solid.y + 5, 22, 9);
      ctx.strokeStyle = "#152119";
      ctx.lineWidth = 5;
      ctx.strokeRect(solid.x, solid.y, solid.w, 25);
      return;
    }

    const tile = solid.type === "crate" ? 54 : 42;
    for (let x = solid.x; x < solid.x + solid.w; x += tile) {
      const width = Math.min(tile, solid.x + solid.w - x);
      ctx.fillStyle = solid.type === "crate" ? "#bd7c39" : "#9b5534";
      ctx.fillRect(x, solid.y, width, solid.h);
      ctx.fillStyle = solid.type === "crate" ? "#e1a44e" : "#c97946";
      ctx.fillRect(x + 5, solid.y + 5, width - 10, 7);
      ctx.strokeStyle = "#4c3426";
      ctx.lineWidth = 4;
      ctx.strokeRect(x, solid.y, width, solid.h);
      if (solid.type === "crate") {
        ctx.beginPath();
        ctx.moveTo(x + 8, solid.y + 8);
        ctx.lineTo(x + width - 8, solid.y + solid.h - 8);
        ctx.moveTo(x + width - 8, solid.y + 8);
        ctx.lineTo(x + 8, solid.y + solid.h - 8);
        ctx.stroke();
      }
    }
  }

  function drawGoal() {
    ctx.fillStyle = "#4a3b67";
    ctx.fillRect(8160, 248, 12, 352);
    ctx.fillStyle = "#ede6fa";
    ctx.fillRect(8164, 252, 96, 58);
    ctx.fillStyle = "#8e69dc";
    ctx.beginPath();
    ctx.moveTo(8172, 252);
    ctx.lineTo(8260, 252);
    ctx.lineTo(8172, 306);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#f385ff";
    ctx.beginPath();
    ctx.arc(8166, 242, 12, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#ddd8e9";
    ctx.fillRect(8270, 410, 130, 190);
    ctx.fillStyle = "#554672";
    ctx.fillRect(8280, 425, 110, 42);
    ctx.fillStyle = "#241c35";
    ctx.fillRect(8310, 512, 48, 88);
    ctx.fillStyle = "#c7f3ff";
    ctx.fillRect(8292, 476, 27, 25);
    ctx.fillRect(8352, 476, 27, 25);
    ctx.fillStyle = "#f7efff";
    ctx.font = "bold 13px 'Press Start 2P', monospace";
    ctx.textAlign = "left";
    ctx.fillText("LAB PSI", 8095, 224);
  }

  function drawPlayer() {
    if (player.invulnerable > 0 && Math.floor(player.invulnerable * 12) % 2 === 0) return;
    const x = Math.round(player.x);
    const y = Math.round(player.y);
    const bob = player.grounded && Math.abs(player.vx) > 20 ? Math.round(Math.sin(player.walkCycle) * 2) : 0;
    const stride = player.grounded ? Math.round(Math.sin(player.walkCycle) * 5) : 4;

    ctx.save();
    ctx.translate(x + player.w / 2, y + bob);
    ctx.scale(player.facing, 1);

    ctx.fillStyle = "rgba(35, 20, 55, 0.28)";
    ctx.fillRect(-20, player.h - bob + 2, 48, 7);

    // Long purple tail, drawn behind the body.
    ctx.strokeStyle = "#7450a2";
    ctx.lineWidth = 10;
    ctx.lineCap = "square";
    ctx.beginPath();
    ctx.moveTo(-5, 39);
    ctx.quadraticCurveTo(-38, 47, -45, 25);
    ctx.quadraticCurveTo(-51, 7, -38, 4);
    ctx.stroke();

    // Legs, feet and pear-shaped torso.
    ctx.fillStyle = "#b8add4";
    ctx.fillRect(-15 - stride, 45, 13, 18);
    ctx.fillRect(7 + stride, 45, 13, 18);
    ctx.fillStyle = "#8063ad";
    ctx.fillRect(-19 - stride, 59, 20, 7);
    ctx.fillRect(7 + stride, 59, 20, 7);
    ctx.fillStyle = "#c9c0df";
    ctx.beginPath();
    ctx.moveTo(-18, 27);
    ctx.quadraticCurveTo(-24, 48, 0, 53);
    ctx.quadraticCurveTo(24, 48, 18, 27);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#77539b";
    ctx.fillRect(-9, 31, 18, 20);

    // Arms and three-finger psychic hand.
    ctx.fillStyle = "#b8add4";
    ctx.fillRect(-23, 25, 10, 25);
    ctx.fillRect(13, 25, 26, 9);
    ctx.fillRect(34, 20, 9, 17);
    ctx.fillRect(40, 18, 9, 5);
    ctx.fillRect(40, 27, 11, 5);
    ctx.fillRect(38, 34, 8, 5);

    // Head, horns and signature purple eyes.
    ctx.fillStyle = "#c9c0df";
    ctx.beginPath();
    ctx.moveTo(-17, 2);
    ctx.lineTo(-13, -13);
    ctx.lineTo(-4, -3);
    ctx.quadraticCurveTo(0, -7, 7, -3);
    ctx.lineTo(17, -13);
    ctx.lineTo(18, 7);
    ctx.quadraticCurveTo(15, 24, 0, 27);
    ctx.quadraticCurveTo(-17, 23, -18, 8);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#7b57a6";
    ctx.fillRect(-11, 8, 8, 5);
    ctx.fillRect(6, 8, 9, 5);
    ctx.fillStyle = "#f2eaff";
    ctx.fillRect(-7, 8, 3, 2);
    ctx.fillRect(10, 8, 3, 2);
    ctx.fillStyle = "#665079";
    ctx.fillRect(-4, 18, 11, 3);

    if (player.muzzle > 0) {
      ctx.globalAlpha = 0.38;
      ctx.fillStyle = "#d36dff";
      ctx.beginPath();
      ctx.arc(51, 26, 20, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#f6c4ff";
      ctx.beginPath();
      ctx.arc(51, 26, 8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawEnemy(enemy) {
    const x = Math.round(enemy.x);
    const y = Math.round(enemy.y + Math.sin(enemy.phase) * 1.5);
    ctx.save();
    ctx.translate(x + enemy.w / 2, y);
    ctx.scale(enemy.vx < 0 ? -1 : 1, 1);
    if (enemy.hit > 0) ctx.globalCompositeOperation = "lighter";

    ctx.fillStyle = "rgba(30, 20, 45, 0.25)";
    ctx.fillRect(-enemy.w / 2, enemy.h - 1, enemy.w, 7);

    if (enemy.kind === 0) {
      // Electric mouse.
      ctx.fillStyle = "#f2cb3f";
      ctx.fillRect(-18, 10, 38, 34);
      ctx.fillRect(-15, -2, 31, 27);
      ctx.beginPath();
      ctx.moveTo(-14, 1);
      ctx.lineTo(-20, -17);
      ctx.lineTo(-5, -2);
      ctx.moveTo(12, 1);
      ctx.lineTo(19, -17);
      ctx.lineTo(4, -2);
      ctx.fill();
      ctx.fillRect(-22, 41, 17, 8);
      ctx.fillRect(7, 41, 17, 8);
      ctx.fillStyle = "#df5146";
      ctx.fillRect(-16, 18, 8, 8);
      ctx.fillRect(10, 18, 8, 8);
      ctx.fillStyle = "#24201e";
      ctx.fillRect(-10, 9, 5, 6);
      ctx.fillRect(7, 9, 5, 6);
      ctx.fillStyle = "#8a6428";
      ctx.fillRect(-31, 18, 13, 9);
      ctx.fillRect(-35, 8, 9, 14);
    } else if (enemy.kind === 1) {
      // Seed-backed grass creature.
      ctx.fillStyle = "#55a98c";
      ctx.fillRect(-22, 18, 44, 27);
      ctx.fillRect(-17, 9, 29, 22);
      ctx.fillStyle = "#317c69";
      ctx.fillRect(-22, 41, 13, 8);
      ctx.fillRect(10, 41, 13, 8);
      ctx.fillStyle = "#dd6680";
      ctx.beginPath();
      ctx.moveTo(-12, 15);
      ctx.lineTo(-17, -4);
      ctx.lineTo(0, 4);
      ctx.lineTo(15, -6);
      ctx.lineTo(12, 16);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "#f4e6dc";
      ctx.fillRect(-11, 16, 6, 7);
      ctx.fillRect(6, 16, 6, 7);
      ctx.fillStyle = "#b44258";
      ctx.fillRect(-9, 18, 4, 5);
      ctx.fillRect(7, 18, 4, 5);
    } else if (enemy.kind === 2) {
      // Fire lizard.
      ctx.fillStyle = "#e8833f";
      ctx.fillRect(-16, 8, 31, 35);
      ctx.fillRect(-12, -2, 27, 25);
      ctx.fillRect(-19, 40, 17, 9);
      ctx.fillRect(7, 40, 17, 9);
      ctx.strokeStyle = "#e8833f";
      ctx.lineWidth = 9;
      ctx.beginPath();
      ctx.moveTo(-14, 34);
      ctx.quadraticCurveTo(-35, 31, -33, 12);
      ctx.stroke();
      ctx.fillStyle = "#ffcf3d";
      ctx.fillRect(-39, 2, 13, 14);
      ctx.fillStyle = "#ef5142";
      ctx.fillRect(-36, -4, 8, 10);
      ctx.fillStyle = "#f4e6dc";
      ctx.fillRect(-6, 7, 6, 8);
      ctx.fillRect(8, 7, 6, 8);
      ctx.fillStyle = "#202020";
      ctx.fillRect(-3, 9, 3, 5);
      ctx.fillRect(10, 9, 3, 5);
    } else {
      // Round fairy singer.
      ctx.fillStyle = "#e7a5c7";
      ctx.beginPath();
      ctx.arc(0, 25, 24, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(-17, 9);
      ctx.lineTo(-14, -9);
      ctx.lineTo(-3, 5);
      ctx.moveTo(14, 8);
      ctx.lineTo(19, -8);
      ctx.lineTo(3, 5);
      ctx.fill();
      ctx.fillStyle = "#5c8f9b";
      ctx.fillRect(-13, 17, 8, 11);
      ctx.fillRect(7, 17, 8, 11);
      ctx.fillStyle = "#f4f7f2";
      ctx.fillRect(-10, 18, 3, 5);
      ctx.fillRect(10, 18, 3, 5);
      ctx.fillStyle = "#b76e99";
      ctx.fillRect(-20, 43, 15, 6);
      ctx.fillRect(7, 43, 15, 6);
    }
    ctx.restore();
  }

  function drawBullet(bullet) {
    const centerX = bullet.x + bullet.w / 2;
    const centerY = bullet.y + bullet.h / 2;
    const trailX = centerX - Math.sign(bullet.vx) * 28;
    ctx.fillStyle = "rgba(146, 87, 255, 0.25)";
    ctx.beginPath();
    ctx.arc(trailX, centerY, 15, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "rgba(222, 129, 255, 0.48)";
    ctx.beginPath();
    ctx.arc(centerX, centerY, 16, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#f7d4ff";
    ctx.beginPath();
    ctx.arc(centerX, centerY, 8, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawParticle(particle) {
    ctx.globalAlpha = clamp(particle.life / particle.maxLife, 0, 1);
    ctx.fillStyle = particle.color;
    ctx.fillRect(Math.round(particle.x), Math.round(particle.y), particle.size, particle.size);
    ctx.globalAlpha = 1;
  }

  function drawHud() {
    ctx.save();
    ctx.fillStyle = "rgba(25, 17, 39, 0.86)";
    ctx.fillRect(24, 22, 350, 82);
    ctx.fillRect(WIDTH - 302, 22, 278, 82);
    ctx.strokeStyle = "rgba(230, 224, 192, 0.75)";
    ctx.lineWidth = 3;
    ctx.strokeRect(24, 22, 350, 82);
    ctx.strokeRect(WIDTH - 302, 22, 278, 82);

    ctx.fillStyle = "#d1c0ec";
    ctx.font = "bold 12px 'Press Start 2P', monospace";
    ctx.textAlign = "left";
    ctx.fillText("MEWTWO", 42, 48);
    ctx.fillText("POKÉMON", 184, 48);
    ctx.fillStyle = "#fff0cc";
    ctx.font = "bold 23px 'Roboto Mono', monospace";
    ctx.fillText("♥".repeat(Math.max(0, player.hp)), 42, 80);
    ctx.fillText(`${kills}/${enemySpawns.length}`, 184, 80);

    ctx.fillStyle = "#d1c0ec";
    ctx.font = "bold 11px 'Press Start 2P', monospace";
    ctx.fillText("PODER PSI", WIDTH - 282, 47);
    ctx.textAlign = "right";
    ctx.fillText("TEMPO", WIDTH - 43, 47);
    ctx.fillStyle = player.ammo < 5 ? "#ef6fa7" : "#d98aff";
    ctx.font = "bold 27px 'Roboto Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillText(`${String(player.ammo).padStart(2, "0")}/${PSI_MAX}`, WIDTH - 282, 80);
    ctx.fillStyle = remainingTime < 30 ? "#ef5144" : "#fff0cc";
    ctx.textAlign = "right";
    ctx.fillText(String(Math.ceil(remainingTime)).padStart(3, "0"), WIDTH - 43, 80);

    if (player.reloading > 0) {
      const progress = 1 - player.reloading / 1.15;
      ctx.fillStyle = "rgba(25, 17, 39, 0.9)";
      ctx.fillRect(WIDTH / 2 - 118, 40, 236, 39);
      ctx.fillStyle = "#6b745f";
      ctx.fillRect(WIDTH / 2 - 103, 62, 206, 7);
      ctx.fillStyle = "#c27cff";
      ctx.fillRect(WIDTH / 2 - 103, 62, 206 * progress, 7);
      ctx.fillStyle = "#fff0cc";
      ctx.font = "bold 10px 'Press Start 2P', monospace";
      ctx.textAlign = "center";
      ctx.fillText("RECUPERANDO PSI", WIDTH / 2, 55);
    }

    ctx.fillStyle = "rgba(25, 17, 39, 0.76)";
    ctx.fillRect(24, HEIGHT - 42, WIDTH - 48, 15);
    ctx.fillStyle = "#443656";
    ctx.fillRect(30, HEIGHT - 37, WIDTH - 60, 5);
    ctx.fillStyle = "#a76ce0";
    ctx.fillRect(30, HEIGHT - 37, (WIDTH - 60) * clamp(player.x / 8150, 0, 1), 5);
    const markerX = 30 + (WIDTH - 60) * clamp(player.x / 8150, 0, 1);
    ctx.fillStyle = "#f08cff";
    ctx.fillRect(markerX - 3, HEIGHT - 42, 7, 15);
    ctx.restore();
  }

  function drawPause() {
    ctx.fillStyle = "rgba(18, 11, 30, 0.7)";
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    ctx.fillStyle = "#d98aff";
    ctx.font = "60px 'Black Ops One', Impact, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("BATALHA PAUSADA", WIDTH / 2, HEIGHT / 2 - 8);
    ctx.fillStyle = "#fff0cc";
    ctx.font = "14px 'Press Start 2P', monospace";
    ctx.fillText("P PARA CONTINUAR", WIDTH / 2, HEIGHT / 2 + 42);
  }

  function draw() {
    drawBackground();
    drawWorld();
    drawHud();
    if (state === "paused") drawPause();
  }

  function frame(now) {
    const dt = Math.min((now - lastFrame) / 1000, 1 / 30);
    lastFrame = now;
    if (state === "running") update(dt);
    if (state !== "menu") draw();
    else {
      elapsed += dt;
      drawBackground();
      drawWorld();
    }
    requestAnimationFrame(frame);
  }

  const keyMap = {
    ArrowLeft: "left",
    KeyA: "left",
    ArrowRight: "right",
    KeyD: "right",
    ArrowUp: "jump",
    KeyW: "jump",
    Space: "jump",
    KeyJ: "shoot",
    KeyF: "shoot",
  };

  window.addEventListener("keydown", (event) => {
    if (keyMap[event.code]) {
      event.preventDefault();
      input[keyMap[event.code]] = true;
      if (keyMap[event.code] === "jump" && !event.repeat) input.jumpQueued = true;
    }
    if (event.code === "KeyR") startReload();
    if (event.code === "KeyP" || event.code === "Escape") togglePause();
    if (event.code === "Enter" && (state === "menu" || state === "lost" || state === "won")) beginGame();
  });

  window.addEventListener("keyup", (event) => {
    if (keyMap[event.code]) input[keyMap[event.code]] = false;
  });

  window.addEventListener("blur", () => {
    input.left = false;
    input.right = false;
    input.jump = false;
    input.shoot = false;
    if (state === "running") togglePause();
  });

  document.querySelectorAll("[data-control]").forEach((button) => {
    const control = button.dataset.control;
    const press = (event) => {
      event.preventDefault();
      ensureAudio();
      input[control] = true;
      if (control === "jump") input.jumpQueued = true;
      button.classList.add("is-pressed");
    };
    const release = (event) => {
      event.preventDefault();
      input[control] = false;
      button.classList.remove("is-pressed");
    };
    button.addEventListener("pointerdown", press);
    button.addEventListener("pointerup", release);
    button.addEventListener("pointercancel", release);
    button.addEventListener("pointerleave", release);
  });

  startButton.addEventListener("click", beginGame);
  restartButton.addEventListener("click", beginGame);
  pauseButton.addEventListener("click", togglePause);
  canvas.addEventListener("pointerdown", () => {
    if (state === "running" && matchMedia("(pointer: fine)").matches) shoot();
  });

  resetGame();
  requestAnimationFrame(frame);
})();
