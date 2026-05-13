# GUI and user interaction
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import keyboard

# File handling
import os
import shutil
from pathlib import Path

# Image handling
from PIL import Image, ImageTk, ExifTags

def main():
    app = MainApp()
    app.mainloop()

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Sorter")
        self.geometry("1000x800")
        self.state('zoomed')

        # Initialize frames
        self.info_frame = InfoFrame(self)
        self.info_frame.pack(fill='x', pady=5)
        
        self.image_display = ImageDisplay(self)
        self.image_display.pack(expand=True, fill='both')
        
        self.control_panel = ControlPanel(self, self.image_display)
        self.control_panel.pack(fill='x', pady=10)
        
        # Setup menu bar
        self.create_menu_bar()
        
        # Setup keyboard shortcuts
        self.setup_keyboard_shortcuts()
        
        # Prompt to select folder on startup
        self.image_display.select_folder()

    def create_menu_bar(self):
        menu_bar = tk.Menu(self)
        self.config(menu=menu_bar)
        
        file_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Folder", command=self.image_display.select_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        
    def setup_keyboard_shortcuts(self):
        keyboard.on_press_key('s', lambda _: self.image_display.star_image())
        keyboard.on_press_key('m', lambda _: self.image_display.move_image())
        keyboard.on_press_key('q', lambda _: self.quit())
        keyboard.on_press_key('right', lambda _: self.image_display.next_image())
        keyboard.on_press_key('left', lambda _: self.image_display.previous_image())

class InfoFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.folder_label = tk.Label(self, text="Folder: None")
        self.folder_label.pack()
        self.file_label = tk.Label(self, text="File: None")
        self.file_label.pack()
        self.counter_label = tk.Label(self, text="0 / 0")
        self.counter_label.pack()

class ImageDisplay(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.current_folder = None
        self.image_files = []
        self.current_image_index = 0
        self.image_label = tk.Label(self)
        self.image_label.pack(expand=True, fill='both')
    
    def select_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing images")
        if not folder:
            if not self.current_folder:
                self.parent.quit()
            return
        
        self.current_folder = folder
        Path(os.path.join(self.current_folder, "starred")).mkdir(exist_ok=True)
        Path(os.path.join(self.current_folder, "archive")).mkdir(exist_ok=True)
        
        self.image_files = [
            f for f in os.listdir(self.current_folder)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))
        ]
        
        if not self.image_files:
            messagebox.showinfo("No Images", "No images found in selected folder!")
            self.parent.quit()
            return
        
        self.current_image_index = 0
        self.show_current_image()

    def show_current_image(self):
        if self.current_image_index >= len(self.image_files):
            messagebox.showinfo("Complete", "All images have been sorted!")
            self.parent.quit()
            return
        
        image_path = os.path.join(self.current_folder, self.image_files[self.current_image_index])
        try:
            image = Image.open(image_path)
            image = self.fix_image_orientation(image)
            image.thumbnail((800, 600))
            photo = ImageTk.PhotoImage(image)
            self.image_label.configure(image=photo)
            self.image_label.image = photo
        except Exception as e:
            print(f"Error loading image {image_path}: {e}")
            self.current_image_index += 1
            self.show_current_image()

    def fix_image_orientation(self, image):
        try:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
            exif = image._getexif()
            if exif and orientation in exif:
                if exif[orientation] == 3:
                    image = image.rotate(180, expand=True)
                elif exif[orientation] == 6:
                    image = image.rotate(270, expand=True)
                elif exif[orientation] == 8:
                    image = image.rotate(90, expand=True)
        except Exception:
            pass
        return image

    def next_image(self):
        if self.current_image_index < len(self.image_files) - 1:
            self.current_image_index += 1
            self.show_current_image()
    
    def previous_image(self):
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self.show_current_image()
    
    def star_image(self):
        self.move_image("starred")
    
    def move_image(self, folder="archive"):
        if self.current_image_index < len(self.image_files):
            src = os.path.join(self.current_folder, self.image_files[self.current_image_index])
            dst = os.path.join(self.current_folder, folder, self.image_files[self.current_image_index])
            try:
                shutil.move(src, dst)
                self.image_files.pop(self.current_image_index)
                self.show_current_image()
            except Exception as e:
                print(f"Error moving file: {e}")

class ControlPanel(ttk.Frame):
    def __init__(self, parent, image_display):
        super().__init__(parent)
        self.image_display = image_display
        
        self.prev_button = ttk.Button(self, text="← Previous", command=self.image_display.previous_image)
        self.prev_button.pack(side='left', padx=5)
        
        self.next_button = ttk.Button(self, text="Next →", command=self.image_display.next_image)
        self.next_button.pack(side='left', padx=5)
        
        self.star_button = ttk.Button(self, text="Star (S)", command=self.image_display.star_image)
        self.star_button.pack(side='right', padx=5)
        
        self.move_button = ttk.Button(self, text="Move (M)", command=self.image_display.move_image)
        self.move_button.pack(side='right', padx=5)

if __name__ == "__main__":
    main()