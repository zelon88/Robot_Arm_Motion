# ------------------------------------------------------------------------------
# APPLICATION NAME
#   Robot_Arm_Motion.py

# APPLICATION INFORMATION
#   Written by Daniel Grimes, Justin Grimes, & Google Gemini.
#   https://github.com/zelon88/Robot_Motion
#   Version v1.0, June 18th, 2026
#   Licensed Under GNU GPLv3

# APPLICATION DESCRIPTION
#   An application to control Robot Arms & other servo-based devices using a Raspberry Pi!
#   Turns a Raspberry Pi computer into a servo controller using a joystick or gamepad!
#   Supports any number of controllers, axis, or servos. 
#   Allows for creating multiple limb / controller pairs.
#   The number of axis' this application can control is limited only by CPU speed & GPIO pin count.

# APPLICATION NOTES
#   This application must be run as root in order to access the GPIO pins.
#   This application creates one control thread which creates one worker thread per servo. 
#   Number of controllers, axis, and servos is arbitrary. 
#   Multiple controllers & servos can be combined to control complex robots with many degrees of motion.

# HARDWARE NOTES: 
#   Compatible with all RPi boards with 40 pin GPIO headers.
#   Compatible with standard R/C servos.
#   Not to be used to directly power servos from RPi GPIO pins!
#   Damage will result from connecting servo power leads directly to the GPIO pins of an RPi!
#   Only connect the signal pin of the servo to the GPIO header of the RPI.
#   Most servos look for a square +5v signal on their signal pin.
#   A +5v square pulse width of 500ms typically represents a servo position of 0 degrees.
#   A +5v square pulse width of 2500ms typically represents a servo position of 180 degrees.
#   The GPIO output voltatge of 3.3v should be sufficient for most standard 1/10th scale R/C servos.
#   Large servos, or servos with strict 5v signal requirements may require an in-line relay w/external +5v.
#   The MIN_PULSE / MAX_PULSE variables are used to control servo pulse witdh.
#   To mix servos of differing pulse widths in the same robot, multiple versions of the application can be run.

# GPIO PIN CONFIGURATION
#   Numbering Style:  BCM
#    Axis 

# CONTROLLER CONFIGURATION
#   This section defines the controller -> axis -> GPIO configuration.
#   This section controls which controller input is assigned to which servo.
#    Structure:
#     CONTROLLER_CONFIGS = {
#         0: { # Primary Controller (e.g., Robot Arm Left)
#             0: {"pin": 17, "delay": 0.01}, # Axis 0 (Left Stick X) -> GPIO 17
#             1: {"pin": 18, "delay": 0.01}, # Axis 1 (Left Stick Y) -> GPIO 18
#             2: {"pin": 23, "delay": 0.01}, # Axis 2 (Left Trigger) -> GPIO 23
#             3: {"pin": 27, "delay": 0.01}, # Axis 3 (Right Stick X) -> GPIO 27
#           ss  4: {"pin": 22, "delay": 0.01}, # Axis 4 (Right Stick Y) -> GPIO 22
#        s },
#         1: { # Secondary Controller (e.g., Robot Arm Right or Grippers)
#             0: {"pin": 24, "delay": 0.01}, # Axis 0 -> GPIO 24
#             1: {"pin": 25, "delay": 0.01}, # Axis 1 -> GPIO 25
#         },
#     }
CONTROLLER_CONFIGS = {
    0: { # Primary Controller (e.g., Robot Arm Left)
        0: {"pin": 17, "delay": 0.01}, # Axis 0 (Left Stick X) -> GPIO 17
        1: {"pin": 18, "delay": 0.01}, # Axis 1 (Left Stick Y) -> GPIO 18
        2: {"pin": 23, "delay": 0.01}, # Axis 2 (Left Trigger) -> GPIO 23
        3: {"pin": 27, "delay": 0.01}, # Axis 3 (Right Stick X) -> GPIO 27
        4: {"pin": 22, "delay": 0.01}, # Axis 4 (Right Stick Y) -> GPIO 22
    },
    1: { # Secondary Controller (e.g., Robot Arm Right or Grippers)
        0: {"pin": 24, "delay": 0.01}, # Axis 0 -> GPIO 24
        1: {"pin": 25, "delay": 0.01}, # Axis 1 -> GPIO 25
    },
}

# GLOBAL PULSE WIDTH CONFIGURATION
#   This section defines the global pulse width for all servos configured by this applcation.
#   If you have to mix servos which require these values to be different from one another;
#     Make another copy of this application & modify these variables to match each servo.
#     Configure one copy of this application for every different servo on your robot.
MIN_PULSE = 500 # 0 degrees
MAX_PULSE = 2500 # 180 degrees
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Load all required libraries.
import os
import threading
import time
# Suppress the Pygame welcome message in the console
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
import pygame
import pigpio
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# A function to create one worker process for each axis.
# Each axis represents one axis, one servo, & one GPIO pin.
def axis_worker_task(joy_id, axis_id, pin, sleep_time, stop_event):
    # Connect to the local pigpio daemon for hardware timing
    pi = pigpio.pi()
    if not pi.connected:
        print(
            f"[Error] Controller {joy_id}, Axis {axis_id} cannot connect to pigpiod."
        )
        return

    print(
        f"[Worker Started] Controller {joy_id} | Axis {axis_id} | Managing GPIO {pin} | Delay {sleep_time}s"
    )

    try:
        # Initialize the target joystick bound to this thread
        joystick = pygame.joystick.Joystick(joy_id)
        if not joystick.get_init():
            joystick.init()

        while not stop_event.is_set():
            # Update the global pygame device events
            pygame.event.pump()

            # Safeguard against runtime disconnection or missing hardware axis
            if axis_id < joystick.get_numaxes():
                axis_value = joystick.get_axis(axis_id)

                # Linear map: float scale (-1.0 to 1.0) to PWM width (500 to 2500)
                pulse_width = MIN_PULSE + ((axis_value + 1.0) / 2.0) * (
                    MAX_PULSE - MIN_PULSE
                )

                pi.set_servo_pulsewidth(pin, int(pulse_width))

            time.sleep(sleep_time)

    except pygame.error:
        print(f"[Disconnect] Loss of controller {joy_id} on Axis {axis_id}")
    finally:
        # Safety clean-up: cut PWM pulse entirely to kill motor torque
        pi.set_servo_pulsewidth(pin, 0)
        pi.stop()
        print(f"[Worker Shutdown] Cleared GPIO {pin}")
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# The main function of the application which controls the creation & desctuction of workers.
def main():
    pygame.init()
    pygame.joystick.init()

    detected_controllers = pygame.joystick.get_count()
    print(f"System boot: Detected {detected_controllers} physical controller(s).")

    stop_signal = threading.Event()
    threads = []

    # Iterates dynamically through your custom multi-layered configuration tree
    for joy_id, axes_mapping in CONTROLLER_CONFIGS.items():
        if joy_id >= detected_controllers:
            print(
                f"[Configuration Warning] Config references Controller Index {joy_id}, but it is not plugged in."
            )
            continue

        for axis_id, setup in axes_mapping.items():
            gpio_pin = setup["pin"]
            loop_delay = setup["delay"]

            # Initialize a unique, isolated tracking thread for this specific control link
            thread = threading.Thread(
                target=axis_worker_task,
                args=(joy_id, axis_id, gpio_pin, loop_delay, stop_signal),
                daemon=True,
            )
            threads.append(thread)
            thread.start()

    print(
        f"Dynamic deployment complete: {len(threads)} active limbs running. Press Ctrl+C to terminate."
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutdown sequence initiated. Signaling worker threads...")
    finally:
        stop_signal.set()
        time.sleep(0.5) # Allow workers brief window to safely dump PWM states
        pygame.quit()
        print("Robot processing pipeline closed successfully.")
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# The main logic of the application.
if __name__ == "__main__":
    main()
# ------------------------------------------------------------------------------
