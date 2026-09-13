import sys
import os
from app import create_app

# Create WSGI application object for Gunicorn / Production Cloud hosts
env_name = os.environ.get("FLASK_ENV", "production" if os.environ.get("PORT") else "development")
app = create_app(env_name)

if __name__ == "__main__":
    # Cloud hosts usually inject PORT. Use PRIMARY_CLOUD without flags for hosted
    # containers; keep --aws/--azure as local simulation shortcuts.
    port_env = os.environ.get("PORT")
    port = int(port_env) if port_env else 5000
    cloud_name = os.environ.get("PRIMARY_CLOUD", "local").lower()
    
    if "--aws" in sys.argv:
        port = int(os.environ.get("AWS_NODE_PORT", "5001"))
        os.environ["PRIMARY_CLOUD"] = "aws"
        cloud_name = "aws"
    elif "--azure" in sys.argv:
        port = int(os.environ.get("AZURE_NODE_PORT", "5002"))
        os.environ["PRIMARY_CLOUD"] = "azure"
        cloud_name = "azure"

    cloud_labels = {
        "aws": "AWS",
        "azure": "Azure",
        "local": "Local"
    }
    cloud_env = cloud_labels.get(cloud_name, cloud_name.upper())

    print("==================================================")
    print(" Starting NovaPay Banking Instance               ")
    print(f" Environment: {cloud_env} ({env_name})          ")
    print(f" Port:        {port}                             ")
    print(f" URL:         http://localhost:{port}            ")
    print("==================================================")
    
    is_debug = (env_name == "development")
    app.run(host="0.0.0.0", port=port, debug=is_debug, use_reloader=False)
