import time

import cv2

from src.detector import SafetyDetector


def process_video(input_path: str, output_path: str):
    detector = SafetyDetector()

    video = cv2.VideoCapture(input_path)

    if not video.isOpened():
        raise FileNotFoundError(f"Could not open video: {input_path}")

    width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = video.get(cv2.CAP_PROP_FPS)

    writer = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height)
    )

    while True:
        success, frame = video.read()

        if not success:
            break

        start_time = time.time()

        result = detector.detect(frame)
        annotated_frame = result.plot()

        elapsed_time = time.time() - start_time
        current_fps = 1 / elapsed_time if elapsed_time > 0 else 0

        cv2.putText(
            annotated_frame,
            f"FPS: {current_fps:.2f}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        writer.write(annotated_frame)
        cv2.imshow("SafeSight AI", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    video.release()
    writer.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    process_video(
        input_path="data/input_videos/sample.mp4",
        output_path="data/output_videos/output.mp4"
    )