import os
import shutil
from datetime import datetime
from PIL import Image  # Requires Pillow: pip install Pillow

def organize_images_by_month(folder_path):
    """
    Organizes images in a folder into subfolders based on the month they were taken.

    Args:
        folder_path (str): The path to the folder containing the images.
    """

    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    for filename in os.listdir(folder_path):
        filepath = os.path.join(folder_path, filename)

        if not os.path.isfile(filepath):
            continue  # Skip directories

        try:
            img = Image.open(filepath)
            exif_data = img._getexif()

            if exif_data and 36867 in exif_data:  # DateTimeOriginal tag
                date_str = exif_data[36867]
                date_obj = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                month_folder_name = date_obj.strftime("%Y-%m")

                month_folder_path = os.path.join(folder_path, month_folder_name)
                os.makedirs(month_folder_path, exist_ok=True) #creates folder if it doesn't exist.
                try:
                    img.close() #close image to prevent resource leaks.
                except:
                    pass #if image was never opened, nothing to close.
                shutil.move(filepath, os.path.join(month_folder_path, filename))
                print(f"Moved '{filename}' to '{month_folder_name}'.")

            else:
                print(f"Warning: No EXIF DateTimeOriginal data found for '{filename}'.")

        except (IOError, OSError, KeyError, ValueError, AttributeError) as e:
            print(f"Error processing '{filename}': {e}")
        except Exception as e:
            print(f"An unexpected error occurred while processing '{filename}': {e}")
        
def main():
    folder_path = input("Enter the folder path containing the images: ")
    organize_images_by_month(folder_path)
    print("Image organization complete.")

if __name__ == "__main__":
    main()