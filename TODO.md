# This file is a list of features that should be added in the application.

---

## General application idea.
I want to write a modular application for linux based devices like raspberry pi's that can show images/gifs/videos/websites.
The application should be modular and easy to add, remove and adjust features.
I want it all to be controlled via a webpage that the device itself hosts.
a really important feature is that I want the application to be updatable from github, the github repo is https://github.com/tpersp/EchoView.git .
I want settings to be persistant across boots or system/service restarts.
I want it to be able to connect to local smb shares, as I have a network folder with a lot of gifs already, they are sorted in different folders and i want to be able to select folders to show from or mix between folders and such.
I also want to be able to connect my spotify, and so it can show the current playing album image+artist name + song name, possibly a bar showing live playback lenght.
For the spotify feature, I want to be able to pick a fallback view, so if I'm not playing anything on spotify, it uses fallback and shows whatever I picked it to show.

---

# Specific ideas.

## Setup.sh
A **setup.sh** that guides the user through the setup.
    The setup.sh should install system services that runs the backend, webpage and the display that shows images/gifs/videos/webpages.
    The setup.sh should ask the user if they want to use local storage for media files, or if it should mount a smb share. If the user choses smb share, it should initialize the connection by asking the user for the needed info, and mount it as a local drive for constant media access. 
    If the user says no to smb share, it should create a local storage for media files, so when they are uploaded via the webpage, they will be stored locally instead of in the smb. 

## Media upload
A way to upload media via the webpage. 
    The media should be saved in either local storage or the mounted smb share, depending on what the user have chosen during the install of the application.