## Installing `pipenv` on MacOS

1. First, let’s check that we have `pip` using the `pip3 --version` command. If you’re using Python 2, you’ll use the `pip --version` command instead.
    
    ```
    My-Mac:~ codecademy$ pip3 --versionpip 18.1 from /usr/lib/python3/dist-packages/pip (python 3.7)
    ```
    
    If you instead see:
    
    ```
    -bash: pip3: command not found
    ```
    
    you may need to update or reinstall Python. [This article about Installing Python 3 and Python Packages can help](https://www.codecademy.com/article/install-python3).
    
2. Next, let’s install `pipenv` using the `pip3 install --user pipenv` command:
    
    ```
    My-Mac:~ codecademy$ pip3 install --user pipenv
    ```
    
    You may see some warnings about certain directories not being on `PATH`. This means, if we try the `pipenv` command, it might not work!
    
    ```
    The scripts pipenv and pipenv-resolver are installed in '/home/yourusername/.local/bin' which is not on PATH.Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location. ... $ pipenv-bash: pipenv: command not found
    ```
    
    Let’s fix that!
    
3. We may need to add the directory `pipenv` is installed in to your `PATH`. We may need to edit our `~/.bash_profile` file using the `vi` editor in our terminal. **If you find yourself getting confused using `vi`, watch the video above to see someone use `vi`.**
    
    ```
    My-Mac:~ codecademy$ vi ~/.bash_profile
    ```
    
    This will open a file with some code already in it! Check for the lines:
    
    ```
    # set PATH so it includes the user's private bin if it existsif [ -d "$HOME/.local/bin" ] ; then  export PATH="$HOME/.local/bin:$PATH"fi
    ```
    
    If your file has these lines, you’re good to go! Skip to the end of this step where we save and exit the file. If you don’t see those lines you will need to add them to your file.
    
    Press the i key to enter `INSERT` mode which allows you to type in the file.
    
    At the bottom of the file, add the lines:
    
    ```
    # set PATH so it includes the user's private bin if it existsif [ -d "$HOME/.local/bin" ] ; then  export PATH="$HOME/.local/bin:$PATH"fi
    ```
    
    Then, we need to save and exit the file. To do this, we need to:
    
    - Press the esc key to exit `INSERT` mode
    - Type `:` which will allow us to enter a `vi` command
    - Press the w key (to save the file), the q key (to exit the file), and ! to force the command
    
    If this is working correctly, the bottom of the file should look like:
    
    ```
    if [ -d "$HOME/.local/bin" ] ; then  PATH="$HOME/.local/bin:$PATH"fi~~:wq!
    ```
    
    Now, press the Enter key.
    
    **Note**: If you don’t see the `:` before the `wq!` this means you’re typing the letters into the file instead of using a `vi` command. Erase the letters and try pressing the esc key to exit `INSERT` mode again.
    
4. Next, we’ll use the command `source ~/.bash_profile` to load these environment variables into the current shell.
    
    ```
    My-Mac:~ codecademy$ source ~/.bash_profile
    ```
    
    Now, typing `pipenv --version` should work!
    
    ```
    My-Mac:~ codecademy$ pipenv --versionpipenv, version 2021.5.29
    ```