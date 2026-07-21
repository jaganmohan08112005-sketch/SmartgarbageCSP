const chintalavalasaWards = {
    "Ward 1 - MVGR College Area": { lat: 18.0552, lon: 83.4051, desc: "Near engineering college campus and hostels" },
    "Ward 2 - Chintalavalasa Junction": { lat: 18.0675, lon: 83.4094, desc: "Main highway junction and commercial shops" },
    "Ward 3 - RTC Colony": { lat: 18.0702, lon: 83.4153, desc: "Residential housing area near RTC layout" },
    "Ward 4 - Ramalayam Street": { lat: 18.0650, lon: 83.4005, desc: "Old village residential sector around temple" },
    "Ward 5 - Sai Nagar": { lat: 18.0751, lon: 83.4201, desc: "New developing residential layout area" }
};

function initializeWardDropdown(selectId, defaultOptionText = "-- Select Ward / Area --") {
    const selector = document.getElementById(selectId);
    if (!selector) return;
    
    selector.innerHTML = `<option value="" disabled selected>${defaultOptionText}</option>`;
    Object.keys(chintalavalasaWards).forEach(ward => {
        let option = document.createElement("option");
        option.value = ward;
        option.textContent = ward;
        selector.appendChild(option);
    });
}
