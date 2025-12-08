import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
import sqlite3

# Function to execute SQL query
def execute_query():
    query = sql_text.get("1.0", tk.END).strip()
    if not query:
        messagebox.showwarning("Empty Query", "Please enter an SQL query.")
        return

    try:
        conn = sqlite3.connect(db_path.get())
        cursor = conn.cursor()
        cursor.execute(query)

        if query.lower().startswith("select"):
            rows = cursor.fetchall()
            result_box.delete("1.0", tk.END)
            for row in rows:
                result_box.insert(tk.END, str(row) + "\n")
        else:
            conn.commit()
            result_box.insert(tk.END, "Query executed successfully.\n")
        conn.close()
    except Exception as e:
        result_box.insert(tk.END, f"Error: {e}\n")

# Function to select a DB file
def browse_file():
    file_path = filedialog.askopenfilename(filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")])
    if file_path:
        db_path.set(file_path)

# GUI Setup
root = tk.Tk()
root.title("SQLite Query Runner")

db_path = tk.StringVar()

tk.Label(root, text="SQLite DB Path:").pack(padx=5, pady=5, anchor="w")
tk.Entry(root, textvariable=db_path, width=60).pack(side="left", padx=5)
tk.Button(root, text="Browse", command=browse_file).pack(side="left", padx=5)

tk.Label(root, text="Enter SQL Query:").pack(padx=5, pady=(10, 0), anchor="w")
sql_text = scrolledtext.ScrolledText(root, width=80, height=10)
sql_text.pack(padx=5, pady=5)

tk.Button(root, text="Run Query", command=execute_query).pack(pady=10)

tk.Label(root, text="Results:").pack(padx=5, pady=(10, 0), anchor="w")
result_box = scrolledtext.ScrolledText(root, width=80, height=15)
result_box.pack(padx=5, pady=5)

root.mainloop()
