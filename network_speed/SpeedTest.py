from flask import Flask, Response
import speedtest
import time
import threading

app = Flask(__name__)
download_speed = 0
upload_speed = 0

def speedtest_thread():
    global download_speed, upload_speed
    while True:
        try:
            s = speedtest.Speedtest()
            s.get_best_server()
            download_speed = s.download() / 1024 / 1024
            upload_speed = s.upload() / 1024 / 1024
            time.sleep(1800)
        except speedtest.ConfigRetrievalError:
            print("Failed to retrieve speedtest configuration. Skipping this round.")
            time.sleep(1800)  
            time.sleep(1800)

@app.route('/metrics')
def metrics():
    global download_speed, upload_speed
    metrics = [
        f'internet_speed_download {download_speed}',
        f'internet_speed_upload {upload_speed}',
    ]
    return Response('\n'.join(metrics), mimetype='text/plain')

if __name__ == '__main__':
    threading.Thread(target=speedtest_thread).start()
    app.run(host='0.0.0.0', port=5000)
