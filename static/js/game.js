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
const gravity = 0.5;
const jumpForce = -10;
const groundY = Math.floor(canvas.height * 0.7);

let score = 0;
let velocityY = 0;
let playerY = groundY;
let playerWidth = 100;
let playerHeight = 100;
let playerX = Math.floor(canvas.width / 2 - playerWidth / 2);
let isGrounded = true;

let obstacles = []; // Array to store obstacles
let obstacleSpeed = 5;
let interval = 100

// Load character running images
const characterImages = [];
const imagePaths = ['/static/images/cow-head.png'];
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
function createObstacle() {
  let obstacle = {
    x: canvas.width, // Start from the right side of the canvas
    y: groundY - 25, // Position above the ground
    width: 25,
    height: 25,
  };
  obstacles.push(obstacle);
}

// Function to update obstacles' positions
function updateObstacles() {
  for (let i = 0; i < obstacles.length; i++) {
    obstacles[i].x -= obstacleSpeed; // Move obstacles from right to left

    // Remove obstacles that go off-screen
    if (obstacles[i].x + obstacles[i].width < 0) {
      obstacles.splice(i, 1);
      i--;
    }
  }
}

// Function to draw obstacles
function drawObstacles() {
  ctx.fillStyle = 'red'; // Set obstacle color
  for (let i = 0; i < obstacles.length; i++) {
    ctx.fillRect(obstacles[i].x, obstacles[i].y, obstacles[i].width, obstacles[i].height);
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
function update() {
  // Clear the canvas
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Update score
  score++;

  // Apply gravity
  velocityY += gravity;

  // Update player position
  playerY += velocityY;

  // Update obstacles
  updateObstacles();
  drawObstacles();

  // Check for ground collisions
  if (playerY + playerHeight >= groundY) {
    playerY = groundY - playerHeight;
    velocityY = 0;
    isGrounded = true;
  }

  // Check for obstacle collisions
  if (checkCollisions()) {
    displayEndScreen(score);
    return;
  }

  // Update animation frame
  animationFrame++;
  if (animationFrame % 5 === 0) { // Change the number to adjust animation speed
    currentFrame = (currentFrame + 1) % numberOfFrames;
  }

  // Trigger obstacles at intervals
  if (interval == 0){
    createObstacle();
    obstacleSpeed = Math.floor(obstacleSpeed * 1.1);
    interval = Math.floor(Math.random() * 150 + 50)
    console.log(interval)
  }
  interval --;


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
  playerY = groundY;
  score = 0;
  obstacleSpeed = 5;
  document.getElementById('endScreen').style.display = 'none';
  update(); // Restart the game loop
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

// Start the game loop
update();
