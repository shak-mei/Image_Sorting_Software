import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

def replace_text_with_image():
    """Replaces the text in the frame with an image."""
    global image_label, text_label  # Access the global labels

    # Load the image
    try:
        image = Image.open("image.jpg")  # Replace "image.jpg" with your image file
        image.thumbnail((600,400))
        photo = ImageTk.PhotoImage(image)

        # Remove the text label
        text_label.destroy()
        messagebox.showinfo("Complete", "All images have been sorted!")
        # Create and display the image label
        image_label = tk.Label(frame, image=photo)
        image_label.image = photo  # Keep a reference to prevent garbage collection
        
        image_label.pack(padx=10, pady=10)

    except FileNotFoundError:
        print("Image file not found.")
        error_label = tk.Label(frame, text="Image not found")
        error_label.pack()

def replace_image_with_text():
    """Replaces the image in the frame with original text."""
    global image_label, text_label
    try:
        image_label.destroy()
    except:
        pass

    text_label = tk.Label(frame, text="This is some text.")
    text_label.pack(padx=10, pady=10)

# Create the main window
root = tk.Tk()
root.title("Text/Image Switcher")

# Create a frame
frame = ttk.Frame(root, padding="10")
frame.pack()

# Create the initial text label
text_label = tk.Label(frame, text="This is some text.")
text_label.pack(padx=10, pady=10)

# Create the button to replace text with image
image_button = ttk.Button(root, text="Show Image", command=replace_text_with_image)
image_button.pack(pady=5)

text_button = ttk.Button(root, text = "Show Text", command=replace_image_with_text)
text_button.pack(pady=5)

# Start the main loop
root.mainloop()