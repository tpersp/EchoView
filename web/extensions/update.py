from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, HTMLResponse
import subprocess
import os
from config import UPDATE_BRANCH, VIEWER_HOME

router = APIRouter()

@router.post("/update_app")
async def update_app(request: Request):
    # Start update: forced reset to origin/{UPDATE_BRANCH}
    try:
        subprocess.check_call(["git", "fetch"], cwd=VIEWER_HOME)
        subprocess.check_call(["git", "checkout", UPDATE_BRANCH], cwd=VIEWER_HOME)
        subprocess.check_call(["git", "reset", "--hard", f"origin/{UPDATE_BRANCH}"], cwd=VIEWER_HOME)
    except subprocess.CalledProcessError as e:
        return JSONResponse(content={"error": f"Git update failed: {e}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Optionally re-run setup.sh if changed
    try:
        subprocess.check_call(["sudo", "bash", "setup.sh", "--auto-update"], cwd=VIEWER_HOME)
    except subprocess.CalledProcessError:
        pass

    # Reboot after update
    subprocess.Popen(["sudo", "reboot"])
    html = """
    <html><head><title>EchoView Update</title></head>
    <body>
      <h2>Update is complete. The system is now rebooting...</h2>
      <p>Please wait for the device to come back online.</p>
      <a href="/">Return to Home Page</a>
      <script>setTimeout(function(){ window.location.href = "/"; }, 10000);</script>
    </body></html>
    """
    return HTMLResponse(content=html)

@router.post("/restart_services")
async def restart_services():
    try:
        subprocess.check_call(["sudo", "systemctl", "restart", "echoview.service"])
        subprocess.check_call(["sudo", "systemctl", "restart", "controller.service"])
    except subprocess.CalledProcessError as e:
        return JSONResponse(content={"error": f"Failed to restart services: {e}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(content={"message": "Services are restarting now..."})

# This file is intentionally left empty. All extension logic is now in web/extensions/*.py.
