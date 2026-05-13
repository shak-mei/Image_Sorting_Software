import os
import shutil
from tkinter import Tk, filedialog, ttk, messagebox
import keyboard
from PIL import Image, ImageTk, ExifTags
import tkinter as tk
from pathlib import Path

class ImageSorter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Image Sorter")
        self.root.geometry("1000x800")
        
        # Initialize variables
        self.current_folder = None
        self.image_files = []
        self.current_image_index = 0
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create main container
        self.main_container = tk.Frame(self.root)
        self.main_container.pack(expand=True, fill='both', padx=10, pady=5)
        
        # Create info frame
        self.create_info_frame()
        
        # Create image frame
        self.create_image_frame()
        
        # Create control panel
        self.create_control_panel()
        
        # Create status bar
        self.create_status_bar()
        
        # Set up keyboard listeners
        self.setup_keyboard_shortcuts()
        
        # Start by selecting folder
        self.select_folder()
    
    def create_menu_bar(self):
        """Create the top menu bar"""
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)
        
        # File menu
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Folder", command=self.select_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit_application)
        
        # View menu
        view_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Settings", command=self.open_settings)
    
    def create_info_frame(self):
        """Create the information display frame"""
        self.info_frame = tk.Frame(self.main_container, bg='black')
        self.info_frame.pack(fill='x', pady=5)
        
        self.folder_label = tk.Label(self.info_frame, text="", fg='white', bg='black')
        self.folder_label.pack()
        
        self.file_label = tk.Label(self.info_frame, text="", fg='white', bg='black')
        self.file_label.pack()
        
        self.counter_label = tk.Label(self.info_frame, text="", fg='white', bg='black')
        self.counter_label.pack()
    
    def create_image_frame(self):
        """Create the main image display frame"""
        self.image_frame = tk.Frame(self.main_container)
        self.image_frame.pack(expand=True, fill='both')
        
        self.image_label = tk.Label(self.image_frame)
        self.image_label.pack(expand=True, fill='both')
    
    def create_control_panel(self):
        """Create the bottom control panel"""
        self.control_frame = tk.Frame(self.main_container)
        self.control_frame.pack(fill='x', pady=10)
        
        # Navigation buttons
        self.prev_button = ttk.Button(self.control_frame, text="← Previous", command=self.previous_image)
        self.prev_button.pack(side='left', padx=5)
        
        self.next_button = ttk.Button(self.control_frame, text="Next →", command=self.next_image)
        self.next_button.pack(side='left', padx=5)
        
        # Action buttons
        self.star_button = ttk.Button(self.control_frame, text="Star (S)", command=self.star_image)
        self.star_button.pack(side='right', padx=5)
        
        self.move_button = ttk.Button(self.control_frame, text="Move (M)", command=self.move_image)
        self.move_button.pack(side='right', padx=5)
    
    def create_status_bar(self):
        """Create the bottom status bar"""
        self.status_bar = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def setup_keyboard_shortcuts(self):
        """Set up keyboard event listeners"""
        keyboard.on_press_key('s', lambda _: self.star_image())
        keyboard.on_press_key('m', lambda _: self.move_image())
        keyboard.on_press_key('q', lambda _: self.quit_application())
        keyboard.on_press_key('right', lambda _: self.next_image())
        keyboard.on_press_key('left', lambda _: self.previous_image())
    
    def select_folder(self):
        """Prompt user to select a folder and initialize image list"""
        folder = filedialog.askdirectory(title="Select folder containing images")
        if not folder:  # User cancelled
            if self.current_folder is None:  # If this is the first time
                self.root.quit()
            return
            
        self.current_folder = folder
        
        # Create required subfolders
        Path(os.path.join(self.current_folder, "starred")).mkdir(exist_ok=True)
        Path(os.path.join(self.current_folder, "archive")).mkdir(exist_ok=True)
        
        # Get list of image files
        self.image_files = [
            f for f in os.listdir(self.current_folder)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))
            and os.path.isfile(os.path.join(self.current_folder, f))
        ]
        
        if not self.image_files:
            messagebox.showinfo("No Images", "No images found in selected folder!")
            self.root.quit()
            return
            
        self.current_image_index = 0
        self.show_current_image()
        self.status_bar.config(text=f"Loaded {len(self.image_files)} images from folder")

    def fix_image_orientation(self, image):
        """Fix image orientation based on EXIF data"""
        try:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
            exif = image._getexif()
            if exif is not None:
                if orientation in exif:
                    if exif[orientation] == 3:
                        image = image.rotate(180, expand=True)
                    elif exif[orientation] == 6:
                        image = image.rotate(270, expand=True)
                    elif exif[orientation] == 8:
                        image = image.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError, TypeError):
            pass
        return image

    def next_image(self):
        """Move to next image without changing file location"""
        if self.current_image_index < len(self.image_files) - 1:
            self.current_image_index += 1
            self.show_current_image()
            self.status_bar.config(text="Showing next image")

    def previous_image(self):
        """Move to previous image without changing file location"""
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self.show_current_image()
            self.status_bar.config(text="Showing previous image")

    def update_info_display(self):
        """Update the information display labels"""
        folder_name = os.path.basename(self.current_folder)
        file_name = self.image_files[self.current_image_index]
        counter = f"Image {self.current_image_index + 1} of {len(self.image_files)}"
        
        self.folder_label.config(text=f"Folder: {folder_name}")
        self.file_label.config(text=f"File: {file_name}")
        self.counter_label.config(text=counter)

    def show_current_image(self):
        """Display the current image"""
        if self.current_image_index >= len(self.image_files):
            messagebox.showinfo("Complete", "All images have been sorted!")
            self.root.quit()
            return
            
        self.update_info_display()
            
        image_path = os.path.join(self.current_folder, self.image_files[self.current_image_index])
        try:
            image = Image.open(image_path)
            image = self.fix_image_orientation(image)
            
            # Calculate scaling to fit window while maintaining aspect ratio
            display_width = self.image_frame.winfo_width() or 800
            display_height = self.image_frame.winfo_height() or 600
            
            # Calculate scaling factors for both dimensions
            width_ratio = display_width / image.width
            height_ratio = display_height / image.height
            
            # Use the smaller ratio to ensure image fits in both dimensions
            scale_factor = min(width_ratio, height_ratio)
            
            # Calculate new dimensions
            new_width = int(image.width * scale_factor)
            new_height = int(image.height * scale_factor)
            
            # Resize image
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(image)
            self.image_label.configure(image=photo)
            self.image_label.image = photo  # Keep a reference
            
        except Exception as e:
            print(f"Error loading image {image_path}: {e}")
            self.status_bar.config(text=f"Error loading image: {e}")
            self.current_image_index += 1
            self.show_current_image()

    def star_image(self):
        """Move current image to starred folder"""
        if self.current_image_index < len(self.image_files):
            src = os.path.join(self.current_folder, self.image_files[self.current_image_index])
            dst = os.path.join(self.current_folder, "starred", self.image_files[self.current_image_index])
            try:
                shutil.move(src, dst)
                self.status_bar.config(text=f"Moved {self.image_files[self.current_image_index]} to starred folder")
                self.image_files.pop(self.current_image_index)
                if self.image_files:
                    self.show_current_image()
            except Exception as e:
                self.status_bar.config(text=f"Error moving file: {e}")

    def move_image(self):
        """Move current image to archive folder"""
        if self.current_image_index < len(self.image_files):
            src = os.path.join(self.current_folder, self.image_files[self.current_image_index])
            dst = os.path.join(self.current_folder, "archive", self.image_files[self.current_image_index])
            try:
                shutil.move(src, dst)
                self.status_bar.config(text=f"Moved {self.image_files[self.current_image_index]} to archive folder")
                self.image_files.pop(self.current_image_index)
                if self.image_files:
                    self.show_current_image()
            except Exception as e:
                self.status_bar.config(text=f"Error moving file: {e}")

    def open_settings(self):
        """Open the settings window"""
        settings = tk.Toplevel(self.root)
        settings.title("Settings")
        settings.geometry("400x300")
        
        # Create settings controls
        tk.Label(settings, text="Settings", font=('Arial', 16)).pack(pady=10)
        
        # Thumbnail size
        tk.Label(settings, text="Thumbnail Size:").pack(pady=5)
        size_var = tk.StringVar(value="Medium")
        size_combo = ttk.Combobox(settings, textvariable=size_var, values=["Small", "Medium", "Large"])
        size_combo.pack(pady=5)
        
        # Auto-advance option
        auto_advance = tk.BooleanVar()
        tk.Checkbutton(settings, text="Auto-advance after action", variable=auto_advance).pack(pady=5)
        
        # Show keyboard shortcuts
        tk.Label(settings, text="Keyboard Shortcuts:", font=('Arial', 12)).pack(pady=10)
        shortcuts = tk.Text(settings, height=6, width=30)
        shortcuts.insert('1.0', "Left Arrow: Previous Image\n"
                              "Right Arrow: Next Image\n"
                              "S: Star Image\n"
                              "M: Move to Archive\n"
                              "Q: Quit Application")
        shortcuts.config(state='disabled')
        shortcuts.pack(pady=5)

    def quit_application(self):
        """Cleanly exit the application"""
        self.root.quit()

    def run(self):
        """Start the main application loop"""
        self.root.mainloop()

if __name__ == "__main__":
    sorter = ImageSorter()
    sorter.run()