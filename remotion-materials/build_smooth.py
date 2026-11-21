"""Prepare neural samples serially on the GPU while CPU workers bake finished actions."""
from concurrent.futures import ThreadPoolExecutor
import cv2
from timing import records
from neural_frames import prepare
from bake import bake_record


if __name__ == '__main__':
    cv2.setNumThreads(1)
    pending = []
    with ThreadPoolExecutor(max_workers=4) as workers:
        for record in records():
            prepare(record)
            pending.append(workers.submit(bake_record, record))
            if len(pending) >= 6:
                pending.pop(0).result()
        for future in pending:
            future.result()
