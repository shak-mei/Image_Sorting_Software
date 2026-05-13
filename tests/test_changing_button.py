import tkinter as tk

def button_click():
    """Cycles the button's text and function through a list of states."""
    global current_state
    current_state = (current_state + 1) % len(states)  # Cycle through states

    button.config(text=states[current_state]["text"], command=states[current_state]["command"])
    label.config(text=f"Button state changed to {states[current_state]['text']}")

def function_one():
    """First function to be executed."""
    label.config(text="Function 1 executed!")

def function_two():
    """Second function to be executed."""
    label.config(text="Function 2 executed!")

def function_three():
    label.config(text="Function 3 executed!")

# Create the main window
root = tk.Tk()
root.title("Cycling Button")

# Create a label to display messages
label = tk.Label(root, text="Press the button!")
label.pack(pady=10)

# Define states as a list of dictionaries
states = [
    {"text": "Function 1", "command": function_one},
    {"text": "Function 2", "command": function_two},
    {"text": "Function 3", "command": function_three},
]

# Initialize current state
current_state = 0

# Create the button with initial text and function
button = tk.Button(root, text=states[current_state]["text"], command=button_click)
button.pack(pady=10)

# Run the main loop
root.mainloop()