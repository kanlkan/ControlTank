import logging
import random
import signal
import sys
import threading
import time
from logging import basicConfig, getLogger, handlers

import cv2

from camera_feeder import CameraFeeder
from control_tank import ControlTank
from face_recognizer import FaceLabel, FaceRecognizer

basicConfig(
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[handlers.SysLogHandler(address="/dev/log")],
)
logger = getLogger(__name__)


class MainSystem:
    CAPTURE_SRC: str = (
        "nvarguscamerasrc sensor_mode=2 ! nvvidconv ! video/x-raw, " "format=(string)I420 ! videoconvert ! appsink"
    )

    def __init__(self) -> None:
        self._main_thread = threading.Thread(target=self._main)
        self._main_thread_started: bool = False
        self._control_tank = ControlTank()
        self._face_recognier = FaceRecognizer()
        self._camera_feeder = CameraFeeder(MainSystem.CAPTURE_SRC)

    def start(self) -> None:
        try:
            self._control_tank.initialize()
            logger.info("control tank initialized")
            self._camera_feeder.start()
            logger.info("camera feeder started")
            time.sleep(3)
            self._main_thread_started = True
            self._main_thread.start()
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
            logger.info("system started")
        except Exception as ex:
            logger.error(f"system encontered exception on startup: {ex}")

    def stop(self) -> None:
        self._camera_feeder.stop()
        self._main_thread_started = False
        self._main_thread.join()

    def _signal_handler(self, signum, stack) -> None:
        logger.info(f"SIGNAL {signum} recieved")
        self.stop()
        sys.exit(1)

    def _one_rotate(self):
        if random.choice((True, False)):
            self._control_tank.turn_clockwise()
        else:
            self._control_tank.turn_counterclockwise()
        time.sleep(10)
        self._control_tank.stop()

    def _search_faces(self) -> None:
        # rotate clockwise little by little
        self._control_tank.turn_clockwise()
        time.sleep(0.7)
        self._control_tank.stop()

    def _follow_me(self, diff: float) -> None:
        if abs(diff) < 20:
            # Move forward for zooming target face
            self._control_tank.move_forward()
            time.sleep(1)
            self._control_tank.stop()
        elif diff > 0:
            self._control_tank.turn_clockwise()
            time.sleep(0.7)
            self._control_tank.stop()
        else:
            self._control_tank.turn_clockwise()
            time.sleep(0.7)
            self._control_tank.stop()

    def _main(self) -> None:
        frame = self._camera_feeder.read()
        if frame is not None:
            frame_height, frame_width, _ = frame.shape
            logger.info(f"frame.shape: {frame.shape}")
            self._one_rotate()

        while frame is not None and self._main_thread_started is True:
            try:
                _, _, faces = self._face_recognier.detect(frame)
                if len(faces) == 0:
                    logger.debug("no faces")
                    self._search_faces()
                else:
                    logger.debug(f"detect faces: {faces}")
                    for face in faces:
                        x, y, w, h = face
                        center = ((x + x + w) / 2, (y + y + h) / 2)
                        # cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 3)
                        label, conf = self._face_recognier.recognize(
                            cv2.resize(
                                cv2.cvtColor(frame[y : y + h, x : x + w], cv2.COLOR_RGB2GRAY),
                                FaceRecognizer.FACE_IMAGE_SIZE,
                            )
                        )
                        logger.debug(f"reognize face: {label}, {conf}")
                        if label == FaceLabel.me.value and conf < FaceRecognizer.FACE_RECOGNITION_CONF_TH:
                            diff = frame_width / 2 - center[0]
                            logger.debug("Follow me!")
                            self._follow_me(diff)
                        else:
                            self._search_faces()

                frame = self._camera_feeder.read()
            except Exception as ex:
                raise (ex)


main_system = MainSystem()
main_system.start()
