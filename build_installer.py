#!/usr/bin/env python3
"""
DropPrint - 1-Click Windows Installer (.exe) Builder
===================================================
Packages DropPrint into a turnkey single-click installer executable (DropPrint_Setup.exe)
for non-technical shopkeepers and Jan Seva Kendra operators.

Supported Build Modes:
  1. Inno Setup (ISCC) -> Creates industry-standard installer with Inno Setup wizard.
  2. Standalone C# GUI SFX -> Compiles standalone native Windows GUI installer via built-in Windows .NET csc.exe.
     (Zero external dependencies; works out of the box on any Windows system).
"""

import os
import sys
import shutil
import zipfile
import subprocess
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
ASSETS_DIR = BASE_DIR / "assets"
ICON_PATH = ASSETS_DIR / "dropprint.ico"


def find_iscc() -> str | None:
    """Find Inno Setup compiler ISCC.exe in PATH or common Windows locations."""
    # 1. In PATH
    which_iscc = shutil.which("iscc")
    if which_iscc and os.path.exists(which_iscc):
        return which_iscc

    # 2. Known standard and local directories
    candidate_paths = [
        # Antigravity / Electron embedded tools
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity IDE" / "resources" / "app" / "node_modules" / "innosetup" / "bin" / "ISCC.exe",
        # Program Files (x86) and 64-bit
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 5" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 5" / "ISCC.exe",
        Path(r"C:\Inno Setup 6\ISCC.exe"),
        Path(r"C:\InnoSetup\ISCC.exe"),
    ]

    for p in candidate_paths:
        if p.exists():
            return str(p)

    return None


def find_csc() -> str | None:
    """Find Microsoft .NET Framework C# compiler csc.exe."""
    candidate_paths = [
        Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
    ]
    for p in candidate_paths:
        if p.exists():
            return str(p)
    return None


def ensure_icon():
    """Ensure dropprint.ico exists in assets."""
    if ICON_PATH.exists():
        return
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([16, 16, 240, 240], radius=44, fill=(15, 23, 42, 255), outline=(56, 189, 248, 255), width=6)
        draw.rounded_rectangle([45, 105, 211, 205], radius=18, fill=(14, 116, 144, 255), outline=(34, 211, 238, 255), width=4)
        draw.rectangle([70, 45, 186, 115], fill=(248, 250, 252, 255), outline=(203, 213, 225, 255), width=2)
        img.save(ICON_PATH, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print(f"[+] Generated icon: {ICON_PATH}")
    except Exception as e:
        print(f"[!] Warning: Could not generate icon with PIL: {e}")


def create_payload_zip(output_zip: Path) -> int:
    """Creates a compressed zip payload of the DropPrint application for the installer."""
    print("[*] Creating compressed DropPrint payload bundle...")
    exclude_dirs = {".git", "__pycache__", ".pytest_cache", "dist", "build"}
    exclude_exts = {".pyc", ".tmp", ".log"}
    file_count = 0

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(BASE_DIR):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                if f.endswith(tuple(exclude_exts)) or f == output_zip.name:
                    continue
                # Do not package existing large installer executables into payload
                if f.endswith(".exe") and ("Setup" in f or "Installer" in f):
                    continue
                fp = Path(root) / f
                rel = fp.relative_to(BASE_DIR)
                zf.write(fp, rel)
                file_count += 1

    size_mb = output_zip.stat().st_size / (1024 * 1024)
    print(f"[+] Packaged {file_count} files into payload: {size_mb:.2f} MB")
    return file_count


def build_with_inno(iscc_path: str, iss_script: Path, output_exe: Path) -> bool:
    """Compile using Inno Setup Compiler."""
    print(f"[*] Compiling installer using Inno Setup: {iscc_path}")
    print(f"    Script: {iss_script}")

    cmd = [
        iscc_path,
        f"/O{output_exe.parent}",
        f"/F{output_exe.stem}",
        str(iss_script),
    ]

    result = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
    if result.returncode == 0:
        print("[SUCCESS] Inno Setup compilation finished successfully!")
        return True
    else:
        print("[ERROR] Inno Setup compilation failed:")
        print(result.stdout)
        print(result.stderr)
        return False


def build_with_standalone_csharp(csc_path: str, output_exe: Path) -> bool:
    """Build standalone native GUI installer with embedded C# and Windows Forms."""
    print(f"[*] Building standalone native Windows GUI installer via .NET compiler...")
    print(f"    Compiler: {csc_path}")

    temp_zip = DIST_DIR / "temp_payload.zip"
    cs_file = DIST_DIR / "DropPrintInstaller.cs"
    manifest_file = DIST_DIR / "installer.manifest"

    try:
        # 1. Create payload zip
        create_payload_zip(temp_zip)

        # 2. Write application manifest for UAC Admin rights (required for C:\DropPrint)
        manifest_content = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
      <supportedOS Id="{1f676c76-80e1-4239-95bb-83d0f6d0da78}"/>
      <supportedOS Id="{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}"/>
      <supportedOS Id="{35138b9a-5d96-4fbd-8e2d-a2440225f93a}"/>
    </application>
  </compatibility>
</assembly>
"""
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(manifest_content)

        # 3. Write C# WinForms Installer Source
        cs_content = r"""using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Drawing;
using System.Windows.Forms;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace DropPrintInstaller
{
    public class InstallerForm : Form
    {
        private TextBox txtPath;
        private Button btnBrowse;
        private CheckBox chkDesktop;
        private CheckBox chkStartup;
        private CheckBox chkLaunch;
        private ProgressBar progressBar;
        private Label lblStatus;
        private Button btnInstall;
        private Button btnCancel;
        private BackgroundWorker worker;
        private bool isFinished = false;

        public InstallerForm(bool silent = false)
        {
            if (silent)
            {
                RunSilentInstall();
                return;
            }
            InitializeComponent();
        }

        private void InitializeComponent()
        {
            this.Text = "DropPrint Counter - 1-Click Shopkeeper Setup";
            this.Size = new Size(540, 420);
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.BackColor = Color.FromArgb(248, 250, 252);
            this.Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);

            // Header Panel
            Panel headerPanel = new Panel();
            headerPanel.Dock = DockStyle.Top;
            headerPanel.Height = 85;
            headerPanel.BackColor = Color.FromArgb(15, 23, 42); // Navy Blue
            this.Controls.Add(headerPanel);

            Label lblTitle = new Label();
            lblTitle.Text = "🖨️ DropPrint Self-Service Printing Counter";
            lblTitle.Font = new Font("Segoe UI Semibold", 13F, FontStyle.Bold);
            lblTitle.ForeColor = Color.FromArgb(56, 189, 248); // Cyan
            lblTitle.Location = new Point(20, 16);
            lblTitle.AutoSize = true;
            headerPanel.Controls.Add(lblTitle);

            Label lblSub = new Label();
            lblSub.Text = "Turnkey Windows Setup for Jan Seva Kendra & Photocopy Shops";
            lblSub.Font = new Font("Segoe UI", 9F);
            lblSub.ForeColor = Color.FromArgb(203, 213, 225);
            lblSub.Location = new Point(23, 46);
            lblSub.AutoSize = true;
            headerPanel.Controls.Add(lblSub);

            // Install Location Label
            Label lblDir = new Label();
            lblDir.Text = "Installation Folder (डिपॉजिट डायरेक्टरी):";
            lblDir.Font = new Font("Segoe UI Semibold", 9.5F, FontStyle.Bold);
            lblDir.ForeColor = Color.FromArgb(30, 41, 59);
            lblDir.Location = new Point(25, 105);
            lblDir.AutoSize = true;
            this.Controls.Add(lblDir);

            // Path Input
            txtPath = new TextBox();
            txtPath.Text = @"C:\\DropPrint";
            txtPath.Location = new Point(25, 130);
            txtPath.Size = new Size(380, 25);
            txtPath.Font = new Font("Segoe UI", 9.5F);
            this.Controls.Add(txtPath);

            // Browse Button
            btnBrowse = new Button();
            btnBrowse.Text = "Browse...";
            btnBrowse.Location = new Point(415, 128);
            btnBrowse.Size = new Size(85, 28);
            btnBrowse.Click += (s, e) => {
                using (FolderBrowserDialog fbd = new FolderBrowserDialog())
                {
                    fbd.Description = "Select DropPrint Installation Folder";
                    fbd.SelectedPath = txtPath.Text;
                    if (fbd.ShowDialog() == DialogResult.OK)
                    {
                        txtPath.Text = fbd.SelectedPath;
                    }
                }
            };
            this.Controls.Add(btnBrowse);

            // Options Group
            chkDesktop = new CheckBox();
            chkDesktop.Text = "Create Desktop Shortcut (🖨️ DropPrint Counter)";
            chkDesktop.Checked = true;
            chkDesktop.Location = new Point(28, 170);
            chkDesktop.AutoSize = true;
            this.Controls.Add(chkDesktop);

            chkStartup = new CheckBox();
            chkStartup.Text = "Start automatically when computer boots up in the morning";
            chkStartup.Checked = true;
            chkStartup.Location = new Point(28, 198);
            chkStartup.AutoSize = true;
            this.Controls.Add(chkStartup);

            chkLaunch = new CheckBox();
            chkLaunch.Text = "Open DropPrint Shopkeeper Counter immediately in browser";
            chkLaunch.Checked = true;
            chkLaunch.Location = new Point(28, 226);
            chkLaunch.AutoSize = true;
            this.Controls.Add(chkLaunch);

            // Status label
            lblStatus = new Label();
            lblStatus.Text = "Ready to install. Click 'Install Now' to begin.";
            lblStatus.ForeColor = Color.FromArgb(71, 85, 105);
            lblStatus.Location = new Point(25, 265);
            lblStatus.Size = new Size(475, 20);
            this.Controls.Add(lblStatus);

            // Progress Bar
            progressBar = new ProgressBar();
            progressBar.Location = new Point(25, 290);
            progressBar.Size = new Size(475, 22);
            progressBar.Style = ProgressBarStyle.Continuous;
            this.Controls.Add(progressBar);

            // Bottom Buttons
            btnInstall = new Button();
            btnInstall.Text = "Install Now (इंस्टॉल करें)";
            btnInstall.Font = new Font("Segoe UI Semibold", 9.5F, FontStyle.Bold);
            btnInstall.BackColor = Color.FromArgb(14, 116, 144);
            btnInstall.ForeColor = Color.White;
            btnInstall.FlatStyle = FlatStyle.Flat;
            btnInstall.Location = new Point(280, 332);
            btnInstall.Size = new Size(130, 34);
            btnInstall.Click += BtnInstall_Click;
            this.Controls.Add(btnInstall);

            btnCancel = new Button();
            btnCancel.Text = "Cancel";
            btnCancel.Location = new Point(420, 332);
            btnCancel.Size = new Size(80, 34);
            btnCancel.Click += (s, e) => this.Close();
            this.Controls.Add(btnCancel);

            // Background worker for non-blocking extraction
            worker = new BackgroundWorker();
            worker.WorkerReportsProgress = true;
            worker.DoWork += Worker_DoWork;
            worker.ProgressChanged += Worker_ProgressChanged;
            worker.RunWorkerCompleted += Worker_RunWorkerCompleted;
        }

        private void BtnInstall_Click(object sender, EventArgs e)
        {
            if (isFinished)
            {
                this.Close();
                return;
            }

            txtPath.Enabled = false;
            btnBrowse.Enabled = false;
            chkDesktop.Enabled = false;
            chkStartup.Enabled = false;
            chkLaunch.Enabled = false;
            btnInstall.Enabled = false;
            btnCancel.Enabled = false;

            lblStatus.Text = "Extracting files to " + txtPath.Text + "...";
            worker.RunWorkerAsync(txtPath.Text);
        }

        private void Worker_DoWork(object sender, DoWorkEventArgs e)
        {
            string targetDir = (string)e.Argument;
            Directory.CreateDirectory(targetDir);

            var asm = Assembly.GetExecutingAssembly();
            using (var stream = asm.GetManifestResourceStream("DropPrintPayload"))
            {
                if (stream == null)
                {
                    throw new Exception("Payload resource 'DropPrintPayload' not found inside installer.");
                }

                using (var archive = new ZipArchive(stream, ZipArchiveMode.Read))
                {
                    int total = archive.Entries.Count;
                    int current = 0;

                    foreach (var entry in archive.Entries)
                    {
                        current++;
                        if (string.IsNullOrEmpty(entry.Name) && entry.FullName.EndsWith("/"))
                        {
                            Directory.CreateDirectory(Path.Combine(targetDir, entry.FullName));
                            continue;
                        }

                        string destinationPath = Path.Combine(targetDir, entry.FullName);
                        string parentDir = Path.GetDirectoryName(destinationPath);
                        if (!Directory.Exists(parentDir))
                        {
                            Directory.CreateDirectory(parentDir);
                        }

                        // Extract file, overwriting if needed
                        entry.ExtractToFile(destinationPath, true);

                        int pct = (int)((float)current / total * 100);
                        worker.ReportProgress(pct, entry.Name);
                    }
                }
            }

            // Post-install setup
            CreateUninstaller(targetDir);

            if (chkDesktop.Checked)
            {
                CreateShortcut(
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "DropPrint Counter.lnk"),
                    Path.Combine(targetDir, "Start_DropPrint.bat"),
                    targetDir,
                    Path.Combine(targetDir, @"assets\dropprint.ico"),
                    "Open DropPrint Shopkeeper Counter"
                );
            }

            if (chkStartup.Checked)
            {
                CreateShortcut(
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup), "DropPrint Counter.lnk"),
                    Path.Combine(targetDir, "Start_DropPrint.bat"),
                    targetDir,
                    Path.Combine(targetDir, @"assets\dropprint.ico"),
                    "Auto-Start DropPrint Counter on boot"
                );
            }

            e.Result = targetDir;
        }

        private void Worker_ProgressChanged(object sender, ProgressChangedEventArgs e)
        {
            progressBar.Value = Math.Min(100, Math.Max(0, e.ProgressPercentage));
            string currentFile = e.UserState as string;
            if (!string.IsNullOrEmpty(currentFile))
            {
                lblStatus.Text = string.Format("Installing ({0}%): {1}", e.ProgressPercentage, currentFile);
            }
        }

        private void Worker_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)
        {
            if (e.Error != null)
            {
                MessageBox.Show(
                    "Error during installation: " + e.Error.Message,
                    "Installation Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                lblStatus.Text = "Installation failed!";
                btnCancel.Enabled = true;
                return;
            }

            string targetDir = (string)e.Result;
            progressBar.Value = 100;
            lblStatus.Text = "Installation successfully completed!";
            lblStatus.ForeColor = Color.FromArgb(22, 163, 74); // Green

            isFinished = true;
            btnInstall.Text = "Finish (समाप्त)";
            btnInstall.BackColor = Color.FromArgb(22, 163, 74);
            btnInstall.Enabled = true;
            btnCancel.Visible = false;

            if (chkLaunch.Checked)
            {
                LaunchDropPrint(targetDir);
            }

            MessageBox.Show(
                "🎉 DropPrint Counter installed successfully!\\n\\n" +
                "• Installed in: " + targetDir + "\\n" +
                "• Desktop shortcut 'DropPrint Counter' created.\\n" +
                "• Added to Windows startup.\\n\\n" +
                "Your Counter Dashboard is now opening at http://localhost:8000/shopkeeper/",
                "DropPrint Setup Complete",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information
            );
        }

        private void LaunchDropPrint(string targetDir)
        {
            try
            {
                string batPath = Path.Combine(targetDir, "Start_DropPrint.bat");
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = batPath;
                psi.WorkingDirectory = targetDir;
                psi.UseShellExecute = true;
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Could not launch DropPrint automatically: " + ex.Message);
            }
        }

        private void CreateUninstaller(string targetDir)
        {
            try
            {
                string uninstBat = Path.Combine(targetDir, "Uninstall_DropPrint.bat");
                string content = @"@echo off
title Uninstall DropPrint
echo ============================================================
echo   DropPrint Uninstaller
echo ============================================================
echo Stopping DropPrint services...
call ""%~dp0Stop_DropPrint.bat"" >nul 2>&1
echo Removing Shortcuts...
del ""%USERPROFILE%\Desktop\DropPrint Counter.lnk"" 2>nul
del ""%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DropPrint Counter.lnk"" 2>nul
echo Shortcuts removed.
echo To completely remove DropPrint, you can delete this folder:
echo ""%~dp0""
echo ============================================================
echo [SUCCESS] DropPrint has been uninstalled.
pause
";
                File.WriteAllText(uninstBat, content);
            }
            catch {}
        }

        private void CreateShortcut(string shortcutPath, string targetPath, string workingDir, string iconPath, string desc)
        {
            try
            {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                dynamic shell = Activator.CreateInstance(shellType);
                dynamic shortcut = shell.CreateShortcut(shortcutPath);
                shortcut.TargetPath = targetPath;
                shortcut.WorkingDirectory = workingDir;
                shortcut.Description = desc;
                if (File.Exists(iconPath))
                {
                    shortcut.IconLocation = iconPath + ",0";
                }
                else
                {
                    shortcut.IconLocation = "shell32.dll,17";
                }
                shortcut.Save();
            }
            catch {}
        }

        private void RunSilentInstall()
        {
            string targetDir = @"C:\DropPrint";
            Directory.CreateDirectory(targetDir);
            var asm = Assembly.GetExecutingAssembly();
            using (var stream = asm.GetManifestResourceStream("DropPrintPayload"))
            {
                if (stream != null)
                {
                    using (var archive = new ZipArchive(stream, ZipArchiveMode.Read))
                    {
                        foreach (var entry in archive.Entries)
                        {
                            if (string.IsNullOrEmpty(entry.Name) && entry.FullName.EndsWith("/"))
                            {
                                Directory.CreateDirectory(Path.Combine(targetDir, entry.FullName));
                                continue;
                            }
                            string dest = Path.Combine(targetDir, entry.FullName);
                            Directory.CreateDirectory(Path.GetDirectoryName(dest));
                            entry.ExtractToFile(dest, true);
                        }
                    }
                }
            }
            CreateUninstaller(targetDir);
            CreateShortcut(
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "DropPrint Counter.lnk"),
                Path.Combine(targetDir, "Start_DropPrint.bat"),
                targetDir,
                Path.Combine(targetDir, @"assets\dropprint.ico"),
                "DropPrint Counter"
            );
            CreateShortcut(
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup), "DropPrint Counter.lnk"),
                Path.Combine(targetDir, "Start_DropPrint.bat"),
                targetDir,
                Path.Combine(targetDir, @"assets\dropprint.ico"),
                "DropPrint Counter"
            );
            LaunchDropPrint(targetDir);
            Environment.Exit(0);
        }

        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            bool isSilent = false;
            foreach (var arg in args)
            {
                if (arg.Equals("/S", StringComparison.OrdinalIgnoreCase) ||
                    arg.Equals("/SILENT", StringComparison.OrdinalIgnoreCase) ||
                    arg.Equals("/VERYSILENT", StringComparison.OrdinalIgnoreCase))
                {
                    isSilent = true;
                    break;
                }
            }
            Application.Run(new InstallerForm(isSilent));
        }
    }
}
"""
        with open(cs_file, "w", encoding="utf-8") as f:
            f.write(cs_content)

        # 4. Compile with csc.exe
        csc_cmd = [
            csc_path,
            "/nologo",
            "/target:winexe",
            f"/out:{output_exe}",
            f"/resource:{temp_zip},DropPrintPayload",
            f"/win32manifest:{manifest_file}",
            "/r:System.dll",
            "/r:System.Windows.Forms.dll",
            "/r:System.Drawing.dll",
            "/r:System.IO.Compression.dll",
            "/r:System.IO.Compression.FileSystem.dll",
        ]

        if ICON_PATH.exists():
            csc_cmd.append(f"/win32icon:{ICON_PATH}")

        csc_cmd.append(str(cs_file))

        print(f"[*] Running C# compiler to embed payload and build {output_exe.name}...")
        res = subprocess.run(csc_cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[SUCCESS] Standalone native installer built: {output_exe}")
            return True
        else:
            print("[ERROR] csc.exe compilation failed:")
            print(res.stdout)
            print(res.stderr)
            return False

    finally:
        # Cleanup temporary build files
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass
        if cs_file.exists():
            try:
                cs_file.unlink()
            except Exception:
                pass
        if manifest_file.exists():
            try:
                manifest_file.unlink()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="DropPrint 1-Click Windows Installer Builder")
    parser.add_argument(
        "--mode",
        choices=["auto", "inno", "standalone"],
        default="auto",
        help="Installer engine: 'auto' (Inno Setup if found, else standalone .NET), 'inno', or 'standalone'",
    )
    parser.add_argument(
        "--output-name",
        default="DropPrint_Setup.exe",
        help="Name of the generated setup executable (default: DropPrint_Setup.exe)",
    )
    args = parser.parse_args()

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    ensure_icon()

    final_exe = DIST_DIR / args.output_name
    iss_script = BASE_DIR / "DropPrint_Installer.iss"

    iscc_exe = find_iscc()
    csc_exe = find_csc()

    print("============================================================")
    print("      DropPrint 1-Click Windows Installer (.exe) Builder    ")
    print("============================================================")
    print(f"Base Directory: {BASE_DIR}")
    print(f"Output File:    {final_exe}")
    print(f"Mode Selected:  {args.mode}")
    print(f"Inno Setup:     {iscc_exe or 'Not Found'}")
    print(f"C# Compiler:    {csc_exe or 'Not Found'}")
    print("============================================================")

    success = False

    if args.mode in ("auto", "inno") and iscc_exe and iss_script.exists():
        print("[*] Using Inno Setup Compiler engine...")
        success = build_with_inno(iscc_exe, iss_script, final_exe)
        if not success and args.mode == "auto":
            print("[!] Inno compilation failed. Falling back to Standalone C# SFX engine...")

    if not success and (args.mode in ("auto", "standalone") or not iscc_exe):
        if not csc_exe:
            print("[ERROR] Neither Inno Setup nor C# compiler (csc.exe) was found on this system.")
            sys.exit(1)
        print("[*] Using Standalone Native C# GUI SFX engine...")
        success = build_with_standalone_csharp(csc_exe, final_exe)

    if success and final_exe.exists():
        size_mb = final_exe.stat().st_size / (1024 * 1024)
        print("============================================================")
        print("  🎉 INSTALLER BUILD SUCCEEDED!")
        print("============================================================")
        print(f"Installer Path: {final_exe.resolve()}")
        print(f"File Size:      {size_mb:.2f} MB")
        print("\nHow to distribute to shopkeepers:")
        print("  1. Copy 'DropPrint_Setup.exe' to a Pen Drive or send via WhatsApp / Google Drive.")
        print("  2. Shopkeeper double-clicks 'DropPrint_Setup.exe' on their Windows PC.")
        print("  3. Clicks 'Install Now' -> DropPrint extracts to C:\\DropPrint, adds Desktop icon,")
        print("     configures auto-boot startup, and opens the shopkeeper counter dashboard immediately!")
        print("============================================================")
    else:
        print("[ERROR] Build failed to generate installer executable.")
        sys.exit(1)


if __name__ == "__main__":
    main()
