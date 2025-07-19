import webview

if __name__ == '__main__':
    webview.create_window('EchoView Display', 'http://localhost:8000/static/display.html', fullscreen=True)
    webview.start()
