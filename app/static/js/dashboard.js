// dashboard.js - extracted from dashboard.html
// External libraries
// Chart.js, chartjs-adapter-date-fns, chartjs-plugin-datalabels are loaded via CDN in the template

// --- Shared Data Fetching for Gear Data ---
let gearDataCache = null;
let gearDataPromise = null;
async function getGearData() {
    if (gearDataCache) return gearDataCache;
    if (!gearDataPromise) {
        gearDataPromise = fetch('/get_gear_data')
            .then(response => response.json())
            .then(jsonData => {
                gearDataCache = jsonData;
                return jsonData;
            });
    }
    return gearDataPromise;
}

// --- Gear Bar Chart JS ---
const predefinedColors = [
    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#E7E9ED', '#4D4D4D'
];
function hexToRgba(hex, alpha = 0.3) {
    hex = hex.replace(/^#/, '');
    let r = parseInt(hex.substring(0, 2), 16);
    let g = parseInt(hex.substring(2, 4), 16);
    let b = parseInt(hex.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
async function fetchLineData() {
    const jsonData = await getGearData();
    return jsonData.lines;
}
function hide_spinner(spinner_id){
    var el = document.getElementById(spinner_id);
    if (el) el.style.display = "none";
}
async function createDistanceChart() {
    const lines = await fetchLineData();
    const distances = lines.map(line => {
        const lastPoint = line.data[line.data.length - 1];
        return lastPoint.y || lastPoint;
    });
    const labels = lines.map(line => line.label);
    const transparentColors = predefinedColors.map(color => hexToRgba(color, 0.3));
    const ctx = document.getElementById('distanceChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                data: distances,
                backgroundColor: transparentColors,
                borderColor: predefinedColors,
                borderWidth: 1
            }]
        },
        options: {
            spanGaps: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    ticks: {
                        font: { size: 14, weight: 'bold' },
                        color: 'black',
                        padding: 20,
                        autoSkip: false,
                        mirror: true
                    }
                },
                x: {
                    title: { display: true, text: 'Distance (mi)' },
                    beginAtZero: true
                },
            },
        }
    });
    hide_spinner("spinner-1-gear");
}
// --- End Gear Bar Chart JS ---

// --- Cumulative Shoe Distances Chart JS ---
async function fetchShoeData() {
    const jsonData = await getGearData();
    return jsonData.lines;
}
async function createShoeChart() {
    const lines = await fetchShoeData();
    const datasets = lines.map((line, index) => ({
        label: line.label,
        data: line.data,
        borderColor: predefinedColors[index % predefinedColors.length],
        fill: false
    }));
    const ctx = document.getElementById('shoeChart').getContext('2d');
    window.shoeChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: datasets
        },
        options: {
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'day'
                    },
                    title: {
                        display: true,
                        text: 'Time'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Distance (mi)'
                    },
                    type: 'logarithmic',
                }
            },
            plugins: {
                title: {
                  display: false,
                  text: "Cumulative Shoe Distances",
                },
                legend: {
                    display: false
                }
            }
        }
    });
    renderShoeCheckboxes(lines);
    hide_spinner("spinner-2-gear");
}
function renderShoeCheckboxes(lines) {
    const checkboxesDiv = document.getElementById('checkboxes');
    checkboxesDiv.innerHTML = '';
    lines.forEach((line, index) => {
        const checkboxWrapper = document.createElement('div');
        checkboxWrapper.className = 'checkbox-label';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'custom-checkbox';
        checkbox.style.borderColor = predefinedColors[index % predefinedColors.length];
        checkbox.style.color = predefinedColors[index % predefinedColors.length];
        checkbox.checked = true;
        checkbox.addEventListener('change', () => {
            const meta = window.shoeChartInstance.getDatasetMeta(index);
            meta.hidden = !meta.hidden;
            window.shoeChartInstance.update();
        });
        checkboxWrapper.appendChild(checkbox);

        const label = document.createElement('label');
        label.textContent = line.label;
        checkboxWrapper.appendChild(label);

        checkboxesDiv.appendChild(checkboxWrapper);
    });
}
// --- End Cumulative Shoe Distances Chart JS ---

// --- Main Dashboard Logic ---
let myChart;
let effortChart;
let activityData;
let effortData;
let effortFilter = "record";
let timeWindow = "w";
let dataset = "hr";
let race = "5k";
let activityTypes = ["all"];
const datasetTitles = {
  "hr": "Average Heart Rate (bpm)",
  "avg_speed": "Average Speed (mph)",
  "kudos": "Kudos",
  "vo2_max": "VO2 Max *estimate",
  "pr_count": "PRs Per Activity",
  "distance": "Activity Distance (miles)"
}
var today = new Date();
var minDate = new Date(today);
minDate.setDate(today.getDate() - 7);

function getData() {
  // AJAX call to Flask endpoint
  fetch('/get_data', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({"activity_types": activityTypes})
  })
  .then(response => {
    // Log the response content to inspect it
    console.log("Response content:", response);

    if (!response.ok) {
      throw new Error('Network response was not ok');
    }
    return response.json();
  })
  .then(data => {
    activityData = JSON.parse(data.data);
    updateChart();
    hide_spinner("spinner-1");
  })
  .catch(error => {
    console.error('There was an error with the request:', error);
  });
}

function getEffortData() {
  // AJAX call to Flask endpoint
  fetch('/get_effort_data', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({"race": race, "effort_filter": effortFilter})
  })
  .then(response => {
    // Log the response content to inspect it
    console.log("Response content:", response);

    if (!response.ok) {
      throw new Error('Network response was not ok');
    }
    return response.json();
  })
  .then(data => {
    effortData = JSON.parse(data.data);
    bestEffortsData = JSON.parse(data.best_efforts);
    updateEffortChart();
    hide_spinner("spinner-2");
    renderRaceEfforts(bestEffortsData);
    hide_spinner("spinner-3");
  })
  .catch(error => {
    console.error('There was an error with the request:', error);
  });
}

// Function to render race efforts in the HTML
function renderRaceEfforts(raceEfforts) {
  const container = document.getElementById('race-efforts-container');
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }
  
  raceEfforts.forEach(effort => {
    if (effort.frmt_time !== null) {
      const raceEffortDiv = document.createElement('div');
      raceEffortDiv.classList.add('w3-container');

      raceEffortDiv.innerHTML = `
        <h5 class="w3-opacity"><b>${effort.name} | ${effort.activity_name} | ${new Date(effort.start_date_local).toLocaleDateString()}</b></h5>
        <p><i class="fa fa-clock-o fa-fw w3-margin-right w3-text-teal"></i>${effort.frmt_time}
        <i class="fa fa-arrows-h fa-fw w3-margin-left w3-text-teal"></i>${effort.distance}
        <i class="fa fa-fast-forward fa-fw w3-margin-left w3-text-teal"></i>${effort.frmt_speed} /mi
        </p>
        <hr class="small-margin">
      `;
      
      container.appendChild(raceEffortDiv);
    }
  });
}

// Function to update chart based on selected time window
function updateChart() {
  let title;
  let units;

  title = activityData[timeWindow]["title"];
  units = activityData["units"][dataset];
  labels = activityData[timeWindow]["dates"];
  values = activityData[timeWindow]["values"][dataset];

  if (myChart){
    var chartConfig = myChart.config;
    chartConfig.data.labels = labels;
    chartConfig.data.datasets[0].data = values;
    chartConfig.data.datasets[0].label = datasetTitles[dataset];
    chartConfig.options.plugins.title.text = title;
    myChart.update();
  } else {
    const chartData = {
      labels: labels,
      datasets: [
        {
          label: datasetTitles[dataset],
          data: values.map(value => (value !== null ? value : NaN)),
          backgroundColor: 'rgba(54, 162, 235, 0.5)',
          borderColor: 'rgba(54, 162, 235, 1)',
          borderWidth: 1,
          hidden: false
        }
      ]
    };

    const ctx = document.getElementById('canvas').getContext('2d');
    myChart = new Chart(ctx, {
      type: 'line',
      data: chartData,
      options: {
        spanGaps: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: true,
            text: title,
          }
        }
      }
    });
  }
}

function updateEffortChart() {
  labels = effortData[race]["labels"];
  values = effortData[race]["values"];
  tips = effortData[race]["tips"];

  if (effortChart){
    var chartConfig = effortChart.config;
    chartConfig.data.labels = labels;
    chartConfig.data.datasets[0].data = values;
    chartConfig.data.datasets[0].label = race;
    chartConfig.options.plugins.title.text = race;
    effortChart.update();
  } else {
    const chartData = {
      labels: labels,
      datasets: [
        {
          label: race,
          data: values.map(value => (value !== null ? value : NaN)),
          backgroundColor: 'rgba(54, 162, 235, 0.5)',
          borderColor: 'rgba(54, 162, 235, 1)',
          borderWidth: 1,
          hidden: false
        }
      ]
    };

    const ctx2 = document.getElementById('canvas2').getContext('2d');
    effortChart = new Chart(ctx2, {
      type: 'line',
      data: chartData,
      options: {
        spanGaps: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: true,
            text: race,
          },
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                var seconds = context.raw;
                var hours = Math.floor(seconds / 3600);
                var minutes = Math.floor((seconds % 3600) / 60);
                var seconds_remain = seconds % 60;
                var formattedTime = '';
                if (hours > 0) {
                    formattedTime += hours + ':';
                }
                formattedTime += (minutes < 10 ? '0' + minutes : minutes) + ':' + (seconds_remain < 10 ? '0' + seconds_remain : seconds_remain);
                var dataIndex = context.dataIndex;
                var pace = tips[dataIndex];
                return " " + formattedTime + ",\n " + pace + " /mi";
              }
            }
          }
        },
        scales: {
          y: {
            type: 'linear',
            ticks: {
              stepSize: 900,
              callback: function(value, index, values) {
                // Convert seconds to HH:mm format
                var hours = Math.floor(value / 3600);
                var minutes = Math.floor((value % 3600) / 60);
                
                var formattedTime = '';
                if (hours > 0) {
                    formattedTime += hours + ':';
                }
                
                formattedTime += (minutes < 10 ? '0' : '') + minutes;
                
                return formattedTime;
              }
            }
        },
        }
    }
    });
}
}

function hide_spinner(spinner_id){
  document.getElementById(spinner_id).style.display = "none";
}

function updateWindow(newTimeWindow) {
  timeWindow = newTimeWindow;
  document.querySelectorAll('.window').forEach(btn => btn.classList.remove('active'));
  document.getElementById(timeWindow).classList.add('active');
  updateChart();
}

function updateEffortFilter(newEffortFilter) {
  effortFilter = newEffortFilter;
  document.querySelectorAll('.effort-filter').forEach(btn => btn.classList.remove('active'));
  document.getElementById("filter-" + effortFilter).classList.add('active');
  getEffortData();
  updateEffortChart();
}

function updateRace(name) {
  race = name;
  document.querySelectorAll('.race').forEach(btn => btn.classList.remove('active'));
  document.getElementById(race).classList.add('active');
  getEffortData();
  updateEffortChart();
}

function updateType(newActivityType) {
  if (newActivityType == "all"){
    document.querySelectorAll('.type').forEach(btn => btn.classList.remove('active'));
    activityTypes = ["all"];
  } else {
    document.getElementById("all").classList.remove('active');
    let index = activityTypes.indexOf("all");
    if (activityTypes.includes("all")) {
      activityTypes.splice(index, 1);
    }
  }
  
  if (document.getElementById(newActivityType).classList.contains("active")) {
    document.getElementById(newActivityType).classList.remove('active');
    let index = activityTypes.indexOf(newActivityType);
    if (activityTypes.includes(newActivityType)) {
      activityTypes.splice(index, 1);
    }
  } else {
    document.getElementById(newActivityType).classList.add('active');
    if (!activityTypes.includes(newActivityType)) {
      activityTypes.push(newActivityType);
    }
  }
  
  if (activityTypes.length == 0) {
    activityTypes = ["all"];
    document.getElementById("all").classList.add('active');
  }
  
  getData();
  updateChart();
}

function updateDataset(newDataset) {
  dataset = newDataset;
  document.querySelectorAll('.dataset').forEach(btn => btn.classList.remove('active'));
  document.getElementById(dataset).classList.add('active');
  updateChart();
}

// Function to toggle dataset visibility
function toggleDataset(index) {
    myChart.data.datasets.forEach((dataset, i) => {
        dataset.hidden = (i !== index) ? true : false;
    });
    myChart.update();
}

async function loadImageData() {
  try {
    const response = await fetch('/get_image_data');
    const data = await response.json();
    const imageContainer = document.getElementById('image-container');
    data.urls.forEach(image => {
          const wrapper = document.createElement('div');
          wrapper.className = 'image-wrapper';
          const link = document.createElement('a');
          const img = document.createElement('img');
          img.src = image.url;
          img.alt = 'Image';
          link.appendChild(img);
          wrapper.appendChild(link);
          imageContainer.appendChild(wrapper);
      });
      hide_spinner("spinner-image");
  } catch (error) {
      console.error('Error getting image info:', error);
  }
}

async function loadProfileData() {
  try {
      const response = await fetch('/get_profile_data');
      const data = await response.json();
      const sportsContainer = document.getElementById('sports-container');
      const clubsContainer = document.getElementById('clubs-container');
      const sortedStats = Object.entries(data.stats).sort((a, b) => b[1].count - a[1].count);
      sortedStats.forEach(([sport, sportData]) => {
          const wrapper = document.createElement('div');
          wrapper.className = 'w3-container list-items';
          const header = document.createElement('h5');
          header.className = 'w3-opacity';
          header.style.marginBottom = '5px';
          header.style.marginTop = '0px';
          header.innerHTML = `<b>${sport.charAt(0).toUpperCase() + sport.slice(1)}</b>`;
          wrapper.appendChild(header);
          const flexContainer = document.createElement('div');
          flexContainer.style.display = 'flex';
          flexContainer.style.justifyContent = 'space-between';
          const activities = document.createElement('p');
          activities.className = 'small-margin';
          activities.textContent = `${sportData.count} activities`;
          flexContainer.appendChild(activities);
          const distance = document.createElement('p');
          distance.className = 'small-margin';
          distance.style.textAlign = 'right';
          distance.textContent = `${sportData.distance.toFixed(0)} miles`;
          flexContainer.appendChild(distance);
          wrapper.appendChild(flexContainer);
          const hr = document.createElement('hr');
          hr.className = 'small-margin';
          wrapper.appendChild(hr);
          sportsContainer.appendChild(wrapper);
      });
      hide_spinner("spinner-sports");
      data.clubs.forEach(club => {
          const wrapper = document.createElement('div');
          wrapper.className = 'w3-container';
          const flexContainer = document.createElement('div');
          flexContainer.style.display = 'flex';
          flexContainer.style.justifyContent = 'space-between';
          const name = document.createElement('h5');
          name.className = 'w3-opacity';
          name.innerHTML = `<b>${club.name}</b>`;
          flexContainer.appendChild(name);
          const memberCount = document.createElement('p');
          memberCount.style.textAlign = 'right';
          memberCount.style.paddingTop = '8px';
          memberCount.textContent = `${club.member_count} Members`;
          flexContainer.appendChild(memberCount);
          wrapper.appendChild(flexContainer);
          const hr = document.createElement('hr');
          hr.className = 'small-margin';
          wrapper.appendChild(hr);
          clubsContainer.appendChild(wrapper);
      });
      hide_spinner("spinner-clubs");
  } catch (error) {
      console.error('Error getting profile info:', error);
  }
}

async function loadHeatmap() {
  try {
      const response = await fetch('/get_heatmap');
      const data = await response.json();
      const heatmapFrame = document.getElementById('heatmapFrame');
      heatmapFrame.src = data.heatmap_path;
  } catch (error) {
      console.error('Error loading heatmap:', error);
  }
}

async function loadActivityTypes() {
  try {
      const response = await fetch('/get_activity_types');
      const data = await response.json();
      const buttonContainer = document.getElementById('activityTypeButtons');
      buttonContainer.innerHTML = '';
      data.activity_types.forEach(activity_type => {
          const button = document.createElement('button');
          button.className = 'chart-button type';
          button.id = activity_type;
          button.innerText = activity_type.charAt(0).toUpperCase() + activity_type.slice(1);
          button.onclick = () => updateType(activity_type);
          buttonContainer.appendChild(button);
      });
  } catch (error) {
      console.error('Error loading activity types:', error);
  }
}

window.addEventListener('DOMContentLoaded', function() {
    createDistanceChart();
    createShoeChart();
    loadImageData();
    loadActivityTypes();
    loadProfileData();
    loadHeatmap();
    getData();
    // getEffortData();
    // createDistanceChart();
});
