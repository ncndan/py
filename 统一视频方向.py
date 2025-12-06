import os
import subprocess
import glob
import shutil

# --- ⚙️ 配置区 (按需修改) ---
INPUT_DIR = "."              # 视频文件所在的目录 (当前目录)
TEMP_DIR = "processed_temp"  # 临时存放处理后视频的目录
OUTPUT_FILE = "final_merged_video.mp4"  # 最终合并文件的名称
VIDEO_EXTS = ("mp4", "mov", "avi", "mkv", "flv", "ts") 

# 🎯 目标分辨率
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

# -----------------------------

def get_encoding_args(mode):
    """
    根据用户选择的模式返回 FFmpeg 参数
    mode 1: CPU (libx264)
    mode 2: GPU (h264_nvenc)
    """
    
    # 基础通用参数 (音频、帧率、时间基)
    common_args = [
        "-r", "30",                    # 强制帧率
        "-video_track_timescale", "15360", # 修复合并进度条的关键
        "-c:a", "aac", 
        "-ar", "44100", 
        "-ac", "2", 
        "-b:a", "192k",
        "-y"
    ]

    if mode == '2':
        # 🚀 GPU 模式 (NVIDIA NVENC)
        # 注意: NVENC 不支持 crf，通常用 -cq 或 -qp，这里用 -cq 26 (画质约等于 crf 23)
        video_args = [
            "-c:v", "h264_nvenc",
            "-preset", "p4",    # p1(最快)-p7(最慢)，p4 是中等平衡
            "-cq", "26",        # 恒定质量模式 (数值越小画质越好)
            "-rc", "vbr"        # 启用动态码率
        ]
        print("⚡ 已启用 NVIDIA GPU 加速 (h264_nvenc)")
    else:
        # 🐢 CPU 模式 (默认 libx264)
        video_args = [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23"
        ]
        print("🐢 已启用 CPU 编码 (libx264)")

    return video_args + common_args

def get_video_dimensions(file_path):
    """获取视频宽高"""
    try:
        command = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", 
            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", file_path
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        dim = result.stdout.strip()
        if 'x' in dim:
            return map(int, dim.split('x'))
    except Exception as e:
        print(f"⚠️ 无法读取文件信息: {os.path.basename(file_path)}")
    return 0, 0

def process_video_file(input_file, output_path, encoding_args):
    """
    处理单个视频，接收动态的 encoding_args
    """
    width, height = get_video_dimensions(input_file)
    if width == 0: return False

    filename = os.path.basename(input_file)
    is_portrait = height > width
    
    print(f"   🎞️ 处理中: {filename} ({width}x{height})")
    
    filters = []
    
    # 1. 旋转逻辑
    if is_portrait:
        print(f"      ↪️ 发现竖屏，正在逆时针旋转 90°...")
        filters.append("transpose=2") 
    
    # 2. 统一分辨率逻辑
    scale_filter = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1"
    )
    filters.append(scale_filter)
    
    # 组合 FFmpeg 命令
    cmd = ["ffmpeg", "-i", input_file]
    cmd.extend(["-vf", ",".join(filters)]) 
    cmd.extend(encoding_args)  # <--- 这里使用传入的参数
    cmd.append(output_path)
    
    try:
        # 这里的 stdout 设为 NULL 是为了不刷屏，想看详情可以删掉 stdout=...
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"      ✅ 转码完成。")
        return True
    except subprocess.CalledProcessError:
        print(f"      ❌ 失败: {filename} (请检查文件是否损坏或显卡驱动)")
        return False

def merge_videos(list_file, output_file):
    """执行合并"""
    print(f"\n🚀 开始合并所有片段到 {output_file} ...")
    if os.path.exists(output_file): os.remove(output_file)
    
    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0", 
        "-i", list_file, 
        "-c", "copy", 
        output_file
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"\n🎉 **大功告成！**")
        print(f"📂 输出文件: {os.path.abspath(output_file)}")
    except subprocess.CalledProcessError:
        print("❌ 合并阶段失败。")

def main():
    print("🎬 视频自动统一与合并工具 (GPU/CPU 选择版)")
    print("------------------------------------------------")
    
    # --- 🆕 新增：用户选择 ---
    print("请选择编码模式：")
    print(" [1] CPU (libx264)    - 默认，兼容性最好，速度较慢")
    print(" [2] GPU (h264_nvenc) - 需要 NVIDIA 显卡，速度极快")
    
    choice = input("\n请输入选项 (1 或 2，回车默认 1): ").strip()
    
    # 获取对应的 FFmpeg 参数
    current_encoding_args = get_encoding_args(choice)
    # -----------------------

    # 1. 清理旧数据
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)
    
    list_file_path = os.path.join(TEMP_DIR, "file_list.txt")
    valid_files = []
    
    # 2. 扫描并处理
    for ext in VIDEO_EXTS:
        files = [f for f in glob.glob(os.path.join(INPUT_DIR, f"*.{ext}")) 
                 if os.path.abspath(f) != os.path.abspath(OUTPUT_FILE)]
        
        for input_file in files:
            temp_name = f"processed_{len(valid_files):04d}.mp4" 
            output_path = os.path.join(TEMP_DIR, temp_name)
            
            # 将参数传递进去
            if process_video_file(input_file, output_path, current_encoding_args):
                abs_path = os.path.abspath(output_path).replace("\\", "/")
                valid_files.append(f"file '{abs_path}'")

    # 3. 写入合并列表
    if not valid_files:
        print("\n⚠️ 未找到视频文件。")
        return

    with open(list_file_path, "w", encoding='utf-8') as f:
        f.write("\n".join(valid_files))

    # 4. 合并
    merge_videos(list_file_path, OUTPUT_FILE)
    
    print(f"\n💡 提示: 临时文件保存在 '{TEMP_DIR}' 目录。")

if __name__ == "__main__":
    main()