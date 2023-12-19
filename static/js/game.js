// Check if fullscreen mode is available and enabled
function toggleFullScreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen(); // Enter fullscreen
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen(); // Exit fullscreen
    }
  }
}

//toggleFullScreen();

// Get the canvas element and its 2D context
const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

// Set canvas width and height to match window size
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

// Game variables
const gravity = 0.75;
const jumpForce = -20;
const groundY = Math.floor(canvas.height * 0.9);

let score = 0;
let velocityY = 0;
let playerY = groundY;
let playerWidth = 150;
let playerHeight = 125;
let playerX = Math.floor(canvas.width / 8);
let isGrounded = true;

let obstacles = []; // Array to store obstacles
let grounds = [];
let lastTime = 0;
let markers = [];
let layer1Speed = 7;
let layer2Speed = 4;
let layer3Speed = 2;
let interval = 100
let markerOffset = 0.25;

// Load character running images
const characterImages = [];
const imagePaths = ['/static/images/cow_cardio/animation/run/1.png', '/static/images/cow_cardio/animation/run/2.png'];
imagePaths.forEach((path) => {
  const img = new Image();
  img.src = path;
  characterImages.push(img);
});

// Define variables for character animation
let currentFrame = 0;
const numberOfFrames = characterImages.length;
let animationFrame = 0;

// Function to handle jump
function jump() {
    if (isGrounded) {
        velocityY = jumpForce;
        isGrounded = false;
    }
}

// Function to create obstacles
function createObstacle(name, speed) {
  let obstacleImage = new Image();
  obstacleImage.src = '/static/images/cow_cardio/obstacles/' + name
  let obstacle = {
    img: obstacleImage,
    x: canvas.width, // Start from the right side of the canvas
    y: groundY - 50, // Position above the ground
    width: 50,
    height: 50,
    speed: speed
  };
  obstacles.push(obstacle);
}

// Function to create mile markers
function createMarker(activity) {
  let marker = {
    name: activity['name'],
    distance: activity['distance'],
    time: activity['time'],
    x: canvas.width,
    y: groundY - 100,
    width: 50,
    height: Math.floor(canvas.height / 5)
  };
  markers.push(marker);
}

function createGround(x) {
    if (x == null){
        x = canvas.width;
    }
    // Load the background image
    const backgroundImage = new Image();
    backgroundImage.src = '/static/images/cow_cardio/background/grass.jpg'; // Replace 'track.png' with your image file path

    let ground = {
        img: backgroundImage,
        x: x,
        y: groundY,
        width: canvas.width,
        height: canvas.height - groundY
    };
    grounds.push(ground);
}

// Function to update all objects' positions
function updateObjects(time) {
  const deltaTime = time - lastTime;
  lastTime = time;
  const foregroundSpeed = layer1Speed * deltaTime / 16; // Adjust divisor for desired speed
  const backgroundSpeed = layer2Speed * deltaTime / 16; // Adjust divisor for desired speed

  // obstacles
  for (let i = 0; i < obstacles.length; i++) {
    obstacles[i].x -= foregroundSpeed; // Move obstacles from right to left

    // Remove obstacles that go off-screen
    if (obstacles[i].x + obstacles[i].width < 0) {
      obstacles.splice(i, 1);
      i--;
    }
  }

  // Ground
  for (let i = 0; i < grounds.length; i++) {
    grounds[i].x -= foregroundSpeed; // Move obstacles from right to left

    // Remove obstacles that go off-screen
    if (grounds[i].x + grounds[i].width < 0) {
      grounds.splice(i, 1);
      i--;
      createGround();
    }
  }
  
  for (let i = 0; i < markers.length; i++) {
    markers[i].x -= backgroundSpeed; // Move markers from right to left

    // Remove markers that go off-screen
    if (markers[i].x + markers[i].width < 0) {
      markers.splice(i, 1);
      i--;
    }
  }
}

// Function to draw obstacles
function drawObjects() {
  // obstacles
  for (let i = 0; i < obstacles.length; i++) {
    ctx.drawImage(obstacles[i].img, obstacles[i].x, obstacles[i].y, obstacles[i].width, obstacles[i].height);
  }

  // Ground
  for (let i = 0; i < grounds.length; i++) {
    ctx.drawImage(grounds[i].img, grounds[i].x, grounds[i].y, grounds[i].width, grounds[i].height);
  }

  // markers
  for (let i = 0; i < markers.length; i++) {
    let lineWidth = 5;
    let lineHeight = markers[i].height;
    // Draw a vertical line
      ctx.fillStyle = 'black';
      ctx.fillRect(markers[i].x, markers[i].y, lineWidth, -lineHeight);

      // Display text on top of the line
      ctx.fillStyle = 'black';
      ctx.font = '14px Arial';
      ctx.fillText(markers[i].name, markers[i].x + lineWidth, markers[i].y - lineHeight - 40);
      ctx.fillText(markers[i].distance, markers[i].x + lineWidth, markers[i].y - lineHeight - 25);
      ctx.fillText(markers[i].time, markers[i].x + lineWidth, markers[i].y - lineHeight - 10);
  }
}

// Function to check for collisions between player and obstacles
function checkCollisions() {
  for (let i = 0; i < obstacles.length; i++) {
    let obstacle = obstacles[i];

    // Check for collision between player and obstacle
    if (
      playerX < obstacle.x + obstacle.width &&
      playerX + playerWidth > obstacle.x &&
      playerY < obstacle.y + obstacle.height &&
      playerY + playerHeight > obstacle.y
    ) {
      // Collision detected
      return true;
      // You can add more actions here (e.g., end game, decrease score, etc.)
    }
  }
  return false;
}

// Function to update the game
function update(time) {
  if (time == null){
    time = 0;
  }
  // Clear the canvas
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Update score
  score++;
  miles = (score / 1000).toFixed(2);

  // Display current score in the upper left corner
  ctx.fillStyle = 'black';
  ctx.font = '40px Arial';
  ctx.fillText('Miles: ' + miles, 20, 50);

  // Apply gravity
  velocityY += gravity;

  // Update player position
  playerY += velocityY;

  // Update obstacles
  updateObjects(time);
  drawObjects();


  // Check for ground collisions
  if (playerY + playerHeight >= groundY) {
    playerY = groundY - playerHeight;
    velocityY = 0;
    isGrounded = true;
  }

  // Check for obstacle collisions
  if (checkCollisions()) {
    displayEndScreen(miles);
    return;
  }

  // Update animation frame
  animationFrame++;
  if (animationFrame % 10 === 0) { // Change the number to adjust animation speed
    currentFrame = (currentFrame + 1) % numberOfFrames;
  }

  // Trigger obstacles at intervals
  if (interval <= 0){
    createObstacle('hurdle.png', layer1Speed);
    interval = Math.floor(Math.random() * 150 + 50)
    console.log(interval)
  }
  interval --;

  // Trigger markers
  for (let i = 0; i < activities.length; i++){
    let offsetDistance = activities[i]['distance'] - markerOffset;
    if (offsetDistance < 0){
        offsetDistance = 0;
    }
    if (Number(miles) == offsetDistance){
      createMarker(activities[i]);
      activities.splice(i, 1);
    }
  }

  // Draw the player
//  ctx.fillStyle = 'black';
//  ctx.fillRect(playerX, playerY, playerWidth, playerHeight);
  ctx.drawImage(characterImages[currentFrame], playerX, playerY, playerWidth, playerHeight);

  // Request animation frame to continuously update the game
  requestAnimationFrame(update);
}

// Event listeners for player actions
document.addEventListener('keydown', function(event) {
  if (event.code === 'Space') {
    jump();
  }
});

// Event listener for touch events
canvas.addEventListener('touchstart', function(event) {
  event.preventDefault(); // Prevent default touch behavior (e.g., scrolling)
  jump();
});

// Event listener for mouse click (fallback for desktop)
canvas.addEventListener('mousedown', function(event) {
  event.preventDefault();
  jump();
});

// Function to display title screen
function displayTitleScreen() {
  document.getElementById('highScoreDisplay').innerText = getHighScore(); // Retrieve high score from storage
  document.getElementById('titleScreen').style.display = 'block';
}

// Function to hide title screen
function hideTitleScreen() {
  document.getElementById('titleScreen').style.display = 'none';
}

// Function to start the game from title screen
function startGame() {
  hideTitleScreen();
  restartGame();
}

// Event listener for play button on title screen
document.getElementById('playButton').addEventListener('click', function() {
  startGame();
});

// Function to display end screen
function displayEndScreen(score) {
  document.getElementById('scoreDisplay').innerText = score;
  document.getElementById('endScreen').style.display = 'block';
}

// Function to restart the game
function restartGame() {
  // Reset game variables, player position, score, etc.
  // Example:
  obstacles = [];
  markers = [];
  grounds = [];
  createGround(0);
  createGround();
  playerY = groundY;
  score = 0;
  document.getElementById('endScreen').style.display = 'none';
  requestAnimationFrame(update); // Restart the game loop
}

// Event listener for restart button
document.getElementById('restartButton').addEventListener('click', function() {
  restartGame();
});

// Event listener for exit button
document.getElementById('exitButton').addEventListener('click', function() {
  // Perform actions to exit the game (e.g., redirect to another page, etc.)
  // Example:
  window.location.href = 'index.html'; // Redirect to exit page
});

// Function to retrieve high score (example using localStorage)
function getHighScore() {
  // Retrieve high score from localStorage or any storage mechanism
  return localStorage.getItem('highScore') || 0;
}

// Function to update and store high score (example using localStorage)
function updateHighScore(score) {
  const currentHighScore = getHighScore();
  if (score > currentHighScore) {
    localStorage.setItem('highScore', score);
  }
}

// Start the game loop
displayTitleScreen();
