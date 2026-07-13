import sys
import random
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone, timedelta

# Ensure UTF-8 stdout encoding to support printing emojis on Windows systems
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from app import create_app, db
from app.models import (Schedule, User, Complaint, SmartBin, WorkerProfile, IncidentLog,
                        AuditLog, SensorHealth, OffloadLog, IllegalDumpReport,
                        WasteDeclaration, BWGDeclaration, PAYTInvoice, FirmwareRelease)

app = create_app()

with app.app_context():
    print("⏳ Recreating database tables...")
    db.drop_all()
    db.create_all()
    print("✅ Database tables recreated successfully!")
    
    # 1. Seed Default Users & Profiles
    print("👤 Seeding default users...")
    admin_user = User(
        username="admin",
        password_hash=generate_password_hash("admin123"),
        role="admin",
        phone="+919876543210"
    )
    regular_user = User(
        username="user",
        password_hash=generate_password_hash("user123"),
        role="citizen",
        phone="+919876543211",
        green_points=120
    )
    worker_user = User(
        username="worker",
        password_hash=generate_password_hash("worker123"),
        role="worker",
        phone="+919876543212"
    )
    driver_user = User(
        username="driver2",
        password_hash=generate_password_hash("driver123"),
        role="worker",
        phone="+919876543213"
    )

    db.session.add(admin_user)
    db.session.add(regular_user)
    db.session.add(worker_user)
    db.session.add(driver_user)
    db.session.commit()

    # Seed Worker Profiles
    print("🚛 Seeding worker profiles...")
    wp1 = WorkerProfile(
        user_id=worker_user.id,
        vehicle_id="CV-01",
        latitude=18.0675,
        longitude=83.4094,
        status="Active",
        performance_rating=4.9
    )
    wp2 = WorkerProfile(
        user_id=driver_user.id,
        vehicle_id="CV-02",
        latitude=18.0552,
        longitude=83.4051,
        status="Idle",
        performance_rating=4.7
    )
    db.session.add(wp1)
    db.session.add(wp2)
    db.session.commit()

    print("✅ Default users created:")
    print("   - Admin: username='admin', password='admin123'")
    print("   - Citizen: username='user', password='user123'")
    print("   - Worker 1: username='worker', password='worker123'")
    print("   - Worker 2: username='driver2', password='driver123'")

    # 2. Seed Chintalavalasa Schedules
    print("📅 Seeding Chintalavalasa collection schedules...")
    chintalavalasa_schedules = [
        Schedule(district="Chintalavalasa", ward="Ward 1 - MVGR College Area", day="Monday", time_slot="06:00 AM - 08:30 AM", vehicle_id="CV-01"),
        Schedule(district="Chintalavalasa", ward="Ward 1 - MVGR College Area", day="Thursday", time_slot="06:00 AM - 08:30 AM", vehicle_id="CV-01"),
        Schedule(district="Chintalavalasa", ward="Ward 2 - Chintalavalasa Junction", day="Tuesday", time_slot="07:00 AM - 09:30 AM", vehicle_id="CV-02"),
        Schedule(district="Chintalavalasa", ward="Ward 2 - Chintalavalasa Junction", day="Friday", time_slot="07:00 AM - 09:30 AM", vehicle_id="CV-02"),
        Schedule(district="Chintalavalasa", ward="Ward 3 - RTC Colony", day="Wednesday", time_slot="06:30 AM - 09:00 AM", vehicle_id="CV-03"),
        Schedule(district="Chintalavalasa", ward="Ward 3 - RTC Colony", day="Saturday", time_slot="06:30 AM - 09:00 AM", vehicle_id="CV-03"),
        Schedule(district="Chintalavalasa", ward="Ward 4 - Ramalayam Street", day="Monday", time_slot="07:30 AM - 10:00 AM", vehicle_id="CV-04"),
        Schedule(district="Chintalavalasa", ward="Ward 4 - Ramalayam Street", day="Thursday", time_slot="07:30 AM - 10:00 AM", vehicle_id="CV-04"),
        Schedule(district="Chintalavalasa", ward="Ward 5 - Sai Nagar", day="Tuesday", time_slot="06:30 AM - 09:00 AM", vehicle_id="CV-05"),
        Schedule(district="Chintalavalasa", ward="Ward 5 - Sai Nagar", day="Friday", time_slot="06:30 AM - 09:00 AM", vehicle_id="CV-05")
    ]
    db.session.add_all(chintalavalasa_schedules)
    db.session.commit()

    # 3. Seed Smart Bins
    print("🗑️ Seeding smart bins...")
    bins = [
        # Ward 1
        SmartBin(hardware_id="BIN-101", latitude=18.0550, longitude=83.4045, level=85, battery_level=92, temperature=28.5, methane=450.0, status="Critical", ward="Ward 1 - MVGR College Area"),
        SmartBin(hardware_id="BIN-102", latitude=18.0560, longitude=83.4060, level=30, battery_level=88, temperature=24.2, methane=45.0, status="Safe", ward="Ward 1 - MVGR College Area"),
        # Ward 2
        SmartBin(hardware_id="BIN-201", latitude=18.0670, longitude=83.4085, level=90, battery_level=94, temperature=35.1, methane=550.0, status="Critical", ward="Ward 2 - Chintalavalasa Junction"),
        SmartBin(hardware_id="BIN-202", latitude=18.0680, longitude=83.4100, level=65, battery_level=79, temperature=29.8, methane=120.0, status="Warning", ward="Ward 2 - Chintalavalasa Junction"),
        # Ward 3
        SmartBin(hardware_id="BIN-301", latitude=18.0700, longitude=83.4150, level=15, battery_level=97, temperature=23.5, methane=30.0, status="Safe", ward="Ward 3 - RTC Colony"),
        SmartBin(hardware_id="BIN-302", latitude=18.0710, longitude=83.4160, level=95, battery_level=82, temperature=72.1, methane=850.0, status="Critical", ward="Ward 3 - RTC Colony"),
        # Ward 4
        SmartBin(hardware_id="BIN-401", latitude=18.0645, longitude=83.4000, level=25, battery_level=91, temperature=25.0, methane=40.0, status="Safe", ward="Ward 4 - Ramalayam Street"),
        SmartBin(hardware_id="BIN-402", latitude=18.0655, longitude=83.4010, level=92, battery_level=86, temperature=28.9, methane=610.0, status="Critical", ward="Ward 4 - Ramalayam Street"),
        # Ward 5
        SmartBin(hardware_id="BIN-501", latitude=18.0750, longitude=83.4195, level=55, battery_level=75, temperature=27.2, methane=90.0, status="Warning", ward="Ward 5 - Sai Nagar"),
        SmartBin(hardware_id="BIN-502", latitude=18.0755, longitude=83.4205, level=10, battery_level=99, temperature=24.0, methane=25.0, status="Safe", ward="Ward 5 - Sai Nagar")
    ]
    db.session.add_all(bins)
    db.session.commit()

    # 4. Seed Incident Logs
    print("🚨 Seeding incident logs...")
    incident_bin = SmartBin.query.filter_by(hardware_id="BIN-302").first()
    incident_bin2 = SmartBin.query.filter_by(hardware_id="BIN-201").first()

    incidents = [
        IncidentLog(
            bin_id=incident_bin.id,
            incident_type="Fire Hazard",
            severity="Critical",
            status="Active",
            description="Extreme temperature alert (72.1°C) detected at MVGR College sector bin. Potential fire hazard inside compartment.",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=25)
        ),
        IncidentLog(
            bin_id=incident_bin.id,
            incident_type="Methane Leak",
            severity="Critical",
            status="Active",
            description="Hazardous methane concentration detected (850 ppm). Exceeded safety threshold.",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=15)
        ),
        IncidentLog(
            bin_id=incident_bin2.id,
            incident_type="Vandalism/Tilt Alert",
            severity="Warning",
            status="Active",
            description="Accelerometer detected tilt angle > 45 degrees. Potential vandalism or accidental impact at Junction.",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=5)
        )
    ]
    db.session.add_all(incidents)
    db.session.commit()

    # 5. Update Worker Geofence configurations
    print("🛰️ Setting worker geofences...")
    import json
    # Sector CV-01
    wp1.sector_polygon = json.dumps([[18.0530,83.4020],[18.0530,83.4080],[18.0590,83.4080],[18.0590,83.4020]])
    wp1.current_lat = 18.0552
    wp1.current_lon = 83.4051
    wp1.geofence_violation = False  # Inside bounds!

    # Sector CV-02
    wp2.sector_polygon = json.dumps([[18.0650,83.4060],[18.0650,83.4120],[18.0710,83.4120],[18.0710,83.4060]])
    wp2.current_lat = 18.0850       # Way out of bounds!
    wp2.current_lon = 83.4250
    wp2.geofence_violation = True   # Triggered!
    db.session.commit()

    # 6. Seed Sensor Health (Predictive Maintenance)
    print("🛠️ Seeding sensor health...")
    sh_records = []
    # Seed healthy sensors for all bins
    for b in bins:
        sh = SensorHealth(
            bin_id=b.id,
            battery_voltage=round(random.uniform(3.6, 4.2), 2),
            calibration_drift=round(random.uniform(0.5, 4.5), 1),
            last_ping=datetime.now(timezone.utc) - timedelta(minutes=random.randint(5, 180)),
            fault_flag=False,
            maintenance_scheduled=False
        )
        sh_records.append(sh)
    db.session.add_all(sh_records)
    db.session.commit()

    # Trigger a calibration drift / battery fault on one of the sensors for predictive maintenance demo
    faulty_bin = SmartBin.query.filter_by(hardware_id="BIN-101").first()
    faulty_sh = SensorHealth.query.filter_by(bin_id=faulty_bin.id).first()
    if faulty_sh:
        faulty_sh.battery_voltage = 2.85  # Below critical threshold!
        faulty_sh.calibration_drift = 18.4
        faulty_sh.last_ping = datetime.now(timezone.utc) - timedelta(hours=26)  # Silent for >24 hours
        faulty_sh.fault_flag = True
        faulty_sh.fault_reason = "Ultrasonic sensor silent for over 24 hours. Battery voltage low (2.85V)."
        faulty_sh.maintenance_scheduled = True
        # Also flag on smart bin
        faulty_bin.sensor_fault = True
        db.session.commit()

    # 7. Seed Audit Logs
    print("🔒 Seeding security audit trail logs...")
    audit_logs = [
        AuditLog(username="admin", role="admin", action="RESOLVE_BIN", target="BIN-302", detail="Bin emptied and status reset to Safe.", ip_address="192.168.1.10"),
        AuditLog(username="admin", role="admin", action="FIRMWARE_UPLOAD", target="Firmware v2.1.3", detail="Developer pushed firmware release build v2.1.3.", ip_address="192.168.1.10"),
        AuditLog(username="worker", role="worker", action="OFFLOAD_LOG", target="YARD-A", detail="Driver CV-01 completed offload of 320kg of verified waste.", ip_address="192.168.1.42"),
        AuditLog(username="user", role="citizen", action="WASTE_DECLARATION", target="Ward 2", detail="Citizen submitted daily 4-stream segregation declaration.", ip_address="192.168.1.105")
    ]
    db.session.add_all(audit_logs)
    db.session.commit()

    # 8. Seed Offload Logs
    print("🚛 Seeding driver offloads...")
    offloads = [
        OffloadLog(worker_id=wp1.id, dump_yard_id="YARD-A (Vizianagaram Central)", weight_kg=350.0, vehicle_id="CV-01", impurity_flagged=False),
        OffloadLog(worker_id=wp2.id, dump_yard_id="YARD-B (East Processing Plant)", weight_kg=480.0, vehicle_id="CV-02", impurity_flagged=True, impurity_detail="CV scan flagged plastics inside biowaste stream.")
    ]
    db.session.add_all(offloads)
    db.session.commit()

    # 9. Seed Anonymous Illegal Dump Reports
    print("🚨 Seeding illegal dump reports...")
    dump_reports = [
        IllegalDumpReport(latitude=18.0565, longitude=83.4040, category="Chemical / Industrial", description="Suspected chemical barrels dumped behind MVGR College campus.", ward="Ward 1 - MVGR College Area", status="Pending"),
        IllegalDumpReport(latitude=18.0725, longitude=83.4180, category="E-Waste / Electronics", description="Pile of broken computer displays and lead-acid batteries left in vacant plot.", ward="Ward 3 - RTC Colony", status="Pending")
    ]
    db.session.add_all(dump_reports)
    db.session.commit()

    # 10. Seed 4-Stream Waste Declarations
    print("🌿 Seeding 4-stream declarations...")
    declarations = [
        WasteDeclaration(user_id=regular_user.id, wet_kg=4.5, dry_kg=2.1, sanitary_kg=0.5, hazardous_kg=0.2, ward="Ward 2 - Chintalavalasa Junction"),
        WasteDeclaration(user_id=regular_user.id, wet_kg=3.8, dry_kg=1.8, sanitary_kg=0.2, hazardous_kg=0.0, ward="Ward 2 - Chintalavalasa Junction")
    ]
    db.session.add_all(declarations)
    db.session.commit()

    # 11. Seed BWG Commercial Declarations
    print("🏢 Seeding Bulk Waste declarations & PAYT...")
    bwg_decls = [
        BWGDeclaration(user_id=regular_user.id, entity_name="Sunrise Apartments Block-C", entity_type="residential", composting_kg=40.0, recyclable_kg=35.0, landfill_kg=45.5, request_bulk_pickup=True, pickup_status="Pending"),
        BWGDeclaration(user_id=regular_user.id, entity_name="Mega Shopping Plaza", entity_type="commercial", composting_kg=85.0, recyclable_kg=90.0, landfill_kg=15.0, request_bulk_pickup=False, pickup_status="N/A")
    ]
    db.session.add_all(bwg_decls)
    db.session.commit()

    # Seed PAYT Invoices (Auto-generate for Sunrise apartments since weight > 100kg)
    invoice = PAYTInvoice(
        user_id=regular_user.id,
        period=datetime.now(timezone.utc).strftime("%B %Y"),
        weight_kg=120.5,
        bin_pickups=4,
        amount_rs=round(120.5 * 1.5, 2),
        status="Unpaid"
    )
    db.session.add(invoice)
    db.session.commit()

    # 12. Seed OTA Firmware Releases
    print("📡 Seeding OTA firmware versions...")
    releases = [
        FirmwareRelease(version="2.1.2", filename="ESP32_bin_v2.1.2.bin", description="Improved ultrasonic sensor calibration routines.", target_bins="ALL", push_status="Pushed", pushed_at=datetime.now(timezone.utc)-timedelta(days=5)),
        FirmwareRelease(version="2.1.3", filename="ESP32_bin_v2.1.3.bin", description="Methane gas threshold sensitivity configuration updates.", target_bins="ALL", push_status="Pending")
    ]
    db.session.add_all(releases)
    db.session.commit()

    print("🎉 Database successfully seeded with all advanced v2 features and telemetry metrics!")


