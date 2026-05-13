import tkinter as tk
from tkinter import messagebox

def on_select(choice):
    messagebox.showinfo("Selection", f"You selected: {choice}")
    popup.destroy()

def show_popup():
    global popup
    popup = tk.Toplevel(root)
    popup.title("Choose an Option")
    popup.geometry("300x200")

    tk.Label(popup, text="Select an option:", font=("Arial", 12)).pack(pady=10)

    options = ["Option 1", "Option 2", "Option 3"]
    for option in options:
        tk.Button(popup, text=option, command=lambda opt=option: on_select(opt)).pack(pady=5)

root = tk.Tk()
root.title("Main Window")
root.geometry("400x300")

tk.Button(root, text="Open Popup", command=show_popup).pack(pady=20)

root.mainloop()
