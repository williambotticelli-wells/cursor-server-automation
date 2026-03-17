
import os
import json
import librosa
import numpy as np
import pandas as pd
import soundfile as sf
import shutil
from typing import List, Tuple, Dict, Optional

import matplotlib.image as mpimg
from matplotlib import pyplot as plt
from repp_beatfinding.beat_detection import do_beat_detection_analysis


def parse_repp_analysis(analysis_str):
    """
    Parse nested JSON strings inside a REPP/psynet analysis field.
    Returns fully expanded dictionaries.
    """

    # ---- 1. Handle NaN / empty ----
    if pd.isna(analysis_str) or analysis_str == "":
        return {}

    # ---- 2. Try parsing outer JSON ----
    try:
        data = json.loads(analysis_str)
    except Exception as e:
        print("❌ Outer json.loads failed:", e)
        return {"_raw": analysis_str}

    # ---- 3. Recursively parse any nested JSON strings ----
    def recursive_parse(value):
        """
        Recursively try json.loads on string fields.
        """
        # Case A: nested dict → traverse
        if isinstance(value, dict):
            return {k: recursive_parse(v) for k, v in value.items()}

        # Case B: list → traverse
        if isinstance(value, list):
            return [recursive_parse(x) for x in value]

        # Case C: string → maybe JSON?
        if isinstance(value, str):
            try:
                # Try to decode as JSON
                nested = json.loads(value)
                return recursive_parse(nested)
            except Exception:
                return value  # keep original string

        # Case D: any other type
        return value

    return recursive_parse(data)



def load_stim_info_from_csv(trial_id: int, df: pd.DataFrame) -> dict:
    row = df[df['id'] == trial_id]
    if row.empty:
        raise ValueError(f"No trial found in CSV for ID: {trial_id}")
    row = row.iloc[0]

    stim_duration = float(row['duration_sec'])

    try:
        analysis_parsed = parse_repp_analysis(row['vars'])
    except Exception as e:
        raise RuntimeError(f"Could not parse 'vars' column for Trial {trial_id}: {e}")

    markers_onsets = []

    analysis_data = analysis_parsed.get('analysis', {})

    # 1. Try the 'output' path (expected for newer psynet/REPP data)
    markers_onsets = analysis_data.get('output', {}).get('markers_onsets_input', [])
    if markers_onsets:
        print(f"  [Markers Found] Used 'output' path for Trial {trial_id}.")

    # 2. If not found, try the 'extracted_onsets' path (based on the "old" function)
    if not markers_onsets:
        # Assuming 'extracted_onsets' is a dict after recursive parsing
        markers_onsets = analysis_data.get('extracted_onsets', {}).get('markers_onsets_input', [])
        if markers_onsets:
            print(f"  [Markers Found] Used 'extracted_onsets' path for Trial {trial_id}.")

    # 3. If still not found, print a warning and use empty list
    if not markers_onsets:
        print(
            f"  [Markers Warning] Could not find 'markers_onsets_input' using either known path for Trial {trial_id}. Using empty list.")

    # Safely extract stim_name
    stim_name = analysis_data.get('stim_name', 'Unknown')
    # -----------------------------------------------------------------

    stim_info = {
        "stim_duration": stim_duration,
        "stim_onsets": [],
        "stim_shifted_onsets": [],
        "onset_is_played": [],
        "markers_onsets": markers_onsets,
        "stim_name": stim_name,
    }

    return stim_info

def extract_trial_id_from_filename(audio_fname: str) -> int:
    """
    Extract trial ID from audio filename.
    
    Expected format: "node_10__trial_7__trial_main_page.wav"
    
    Args:
        audio_fname: Audio filename
        
    Returns:
        trial_id: Integer trial ID
    """
    parts = audio_fname.split("__")
    trial_id = int(parts[1].split("_")[1])
    return trial_id


def convert_and_save_audio(
    audio_path: str, 
    output_path: str, 
    target_sr: int = 44100,
    overwrite: bool = False
) -> Tuple[np.ndarray, int]:
    """
    Convert audio file to mono and resample to target sample rate.
    
    Args:
        audio_path: Path to input audio file
        output_path: Path to save converted audio
        target_sr: Target sample rate (default: 44100)
        overwrite: Whether to overwrite existing file (default: False)
        
    Returns:
        Tuple of (audio_data, sample_rate)
    """
    if not overwrite and os.path.exists(output_path):
        # Load existing file instead of converting
        data, fs = sf.read(output_path)
        return data, fs
    
    # Read audio file
    data, fs = sf.read(audio_path)
    
    # Convert to mono if stereo
    if len(data.shape) == 2:
        data = np.mean(data, axis=1)
    
    # Resample if needed
    if fs != target_sr:
        data = librosa.resample(data, orig_sr=fs, target_sr=target_sr)
        fs = target_sr
    
    # Save converted audio
    sf.write(output_path, data, fs, subtype='PCM_16')
    # print(f"WAV converted and saved to {os.path.dirname(output_path)}")
    
    return data, fs


def setup_participant_directories(
    base_dir: str,
    choose_sub_dir: str,
    choose_participant_id: int,
    output_dir: str
) -> Tuple[str, str, List[str]]:
    """
    Set up and validate participant directories.
    
    Args:
        base_dir: Base directory containing assets
        choose_sub_dir: Subdirectory name (e.g., "Task 1")
        choose_participant_id: Participant ID
        output_dir: Output directory for processed files
        
    Returns:
        Tuple of (participant_dir, output_participant_dir, participant_audio_fnames)
        
    Raises:
        ValueError: If participant directory does not exist
    """
    participant_dir = os.path.join(
        base_dir, "assets", choose_sub_dir, "participants", 
        f"participant_{choose_participant_id}"
    )
    output_participant_dir = os.path.join(output_dir, f"participant_{choose_participant_id}")
    
    if not os.path.exists(participant_dir):
        raise ValueError(
            f"Participant directory does not exist: {participant_dir}. "
            f"Choose another participant id."
        )
    
    participant_audio_fnames = [f for f in os.listdir(participant_dir) if f.endswith('.wav')]
    os.makedirs(output_participant_dir, exist_ok=True)
    
    return participant_dir, output_participant_dir, participant_audio_fnames


def process_participant_audio_files(
    participant_dir: str,
    output_participant_dir: str,
    TapTrialMusic_df: pd.DataFrame,
    overwrite: bool = False
) -> List[Tuple[str, str, str]]:
    """
    Process all audio files for a participant: convert audio and extract stimulus info.
    
    Args:
        participant_dir: Directory containing participant audio files
        output_participant_dir: Directory to save processed files
        TapTrialMusic_df: DataFrame containing trial metadata
        overwrite: Whether to overwrite existing files (default: False)
        
    Returns:
        List of tuples: (audio_basename, audio_fname, stim_info_fname)
    """
    participant_audio_fnames = [f for f in os.listdir(participant_dir) if f.endswith('.wav')]
    audio_stim_pairs = []
    
    for audio_fname in participant_audio_fnames:
        # Remove .wav extension to get basename
        audio_basename = os.path.splitext(audio_fname)[0]
        trial_id = extract_trial_id_from_filename(audio_fname)
        
        audio_path = os.path.join(participant_dir, audio_fname)
        output_audio_path = os.path.join(output_participant_dir, audio_fname)
        
        # Convert and save WAV file
        convert_and_save_audio(audio_path, output_audio_path, overwrite=overwrite)
        
        # Extract and save stimulus info
        stim_info = load_stim_info_from_csv(trial_id, TapTrialMusic_df)
        stim_info_json_path = os.path.join(
            output_participant_dir, f"{audio_basename}_stim_info.json"
        )
        
        if overwrite or not os.path.exists(stim_info_json_path):
            with open(stim_info_json_path, 'w') as f:
                json.dump(stim_info, f, indent=4)
            # print(f"stim_info saved: {audio_basename}_stim_info.json")
        
        audio_stim_tup = (audio_basename, audio_fname, f"{audio_basename}_stim_info.json")
        audio_stim_pairs.append(audio_stim_tup)
    
    print(f"WAV files converted and saved to {output_participant_dir}")
    print(f"Stim_info files saved to {output_participant_dir}")
    
    return audio_stim_pairs


def run_repp_analysis_for_participant(
    audio_stim_pairs: List[Tuple[str, str, str]],
    output_participant_dir: str,
    config,
    title_plot: str = 'Beat Finding Analysis',
    display_plots: bool = True,
    figsize: Tuple[int, int] = (14, 12)
) -> List[Dict]:
    """
    Run REPP beat detection analysis for all participant recordings.
    
    Args:
        audio_stim_pairs: List of tuples (basename, audio_fname, stim_info_fname)
        output_participant_dir: Directory containing processed files
        config: REPP configuration object
        title_plot: Title for plots
        display_plots: Whether to display plots inline (default: True)
        figsize: Figure size for plots (default: (14, 12))
        
    Returns:
        List of analysis results dictionaries
    """
    
    
    results = []
    
    for recording_basename, recording_fname, stim_info_fname in audio_stim_pairs:
        # Define filenames for outputs
        plot_filename = f'{recording_basename}.png'
        recording_path = os.path.join(output_participant_dir, recording_fname)
        plot_path = os.path.join(output_participant_dir, plot_filename)
        stim_info_path = os.path.join(output_participant_dir, stim_info_fname)
        
        # Load stimulus info
        with open(stim_info_path, 'r') as f:
            stim_info = json.load(f)
        
        print("-------------------------------------------------\n Running REPP\n")
        
        # Run REPP analysis
        output, extracted_onsets, stats = do_beat_detection_analysis(
            recording_path,
            title_plot,
            plot_path,
            stim_info=stim_info,
            config=config
        )
        
        print("extracted onsets:-----------------------------\n")
        print(extracted_onsets)
        print("-------------------------------------------------\n")
        
        # Display plot if requested
        if display_plots:
            display_analysis_plot(plot_path, figsize=figsize)
        
        results.append({
            'recording_basename': recording_basename,
            'extracted_onsets': extracted_onsets,
            'stats': stats,
            'output': output
        })
    
    return results


def display_analysis_plot(plot_path: str, figsize: Tuple[int, int] = (14, 12)):
    """
    Display analysis plot from saved image file.
    
    Args:
        plot_path: Path to saved plot image
        figsize: Figure size (default: (14, 12))
    """
    
    plt.clf()
    plt.figure(figsize=figsize)
    img = mpimg.imread(plot_path)
    imgplot = plt.imshow(img)
    plt.axis('off')
    plt.tight_layout()





def main_process_all_participants(
        base_dir: str,
        output_dir: str,
        choose_sub_dir: str,
        TapTrialMusic_df: pd.DataFrame,
        overwrite: bool = False
):
    """
    Finds all participant folders for a given task and runs the file processing
    pipeline on each one sequentially.
    """

    # Define the directory where all participant folders are located
    participants_root_dir = os.path.join(
        base_dir, "assets", choose_sub_dir, "participants"
    )

    if not os.path.exists(participants_root_dir):
        print(f"❌ Error: Participants root directory not found: {participants_root_dir}")
        return

    # 1. Identify all participant folders and extract IDs
    participant_folders = [
        f for f in os.listdir(participants_root_dir)
        if f.startswith('participant_') and os.path.isdir(os.path.join(participants_root_dir, f))
    ]

    participant_ids = []
    for folder in participant_folders:
        try:
            # Extracts the number from 'participant_X'
            p_id = int(folder.split('_')[1])
            participant_ids.append(p_id)
        except Exception:
            # Skip folders that don't match the expected naming convention
            continue

    print(f"--- FOUND {len(participant_ids)} PARTICIPANTS TO PROCESS ---")
    print(f"IDs found: {sorted(participant_ids)}")
    print("-" * 50)

    all_results = {}

    # 2. Loop through each participant ID
    for p_id in sorted(participant_ids):
        print(f"\n=======================================================")
        print(f"🚀 STARTING PROCESSING FOR PARTICIPANT ID: {p_id}")
        print(f"=======================================================")

        try:
            participant_dir, output_participant_dir, _ = setup_participant_directories(
                base_dir, choose_sub_dir, p_id, output_dir
            )

            audio_stim_pairs = process_participant_audio_files(
                participant_dir,
                output_participant_dir,
                TapTrialMusic_df,
                overwrite=overwrite
            )


            all_results[p_id] = {'files_processed': len(audio_stim_pairs), 'output_path': output_participant_dir}

        except ValueError as e:
            print(f"❌ Skipping P-{p_id}: {e}")
        except Exception as e:
            print(f"🚨 CRITICAL ERROR processing P-{p_id}: {e}")

    print(f"\n=======================================================")
    print("✨ ALL PARTICIPANTS PROCESSING COMPLETE.")
    print(f"Total processed: {len(all_results)} / {len(participant_ids)}")
    print("=======================================================")

    return all_results




def run_single_repp_trial(base_output_dir, participant_id, node_id, config):
    """
    Run REPP beat analysis for a single trial.

    base_output_dir: path to the 'output' folder
    participant_id: directory name (e.g. 'participant_1')
    node_id: e.g. 'node_7'
    config: REPP config object (e.g. long_tapping)
    """

    participant_dir = os.path.join(base_output_dir, participant_id)

    wav_file = None
    stim_file = None

    for fname in os.listdir(participant_dir):
        if fname.startswith(node_id) and fname.endswith(".wav"):
            wav_file = os.path.join(participant_dir, fname)
        if fname.startswith(node_id) and fname.endswith("_stim_info.json"):
            stim_file = os.path.join(participant_dir, fname)

    if wav_file is None or stim_file is None:
        raise FileNotFoundError(
            f"Could not find both WAV and JSON for {node_id} in {participant_id}"
        )

    # Load stim info
    with open(stim_file, "r") as f:
        stim_info = json.load(f)

    # Create a separate plots folder
    plots_dir = os.path.join(base_output_dir, "plots_single_trial")
    os.makedirs(plots_dir, exist_ok=True)

    # Output plot file
    plot_filename = os.path.join(plots_dir, f"{participant_id}_{node_id}_beat_finding_plot.png")

    print("-------------------------------------------------")
    print(f"Running REPP analysis for {participant_id} - {node_id}")
    print("WAV:", wav_file)
    print("JSON:", stim_file)
    print("Plot will be saved to:", plot_filename)
    print("-------------------------------------------------")

    # Run beat detection
    output, extracted_onsets, stats = do_beat_detection_analysis(
        wav_file,
        f"Beat Finding Analysis – {node_id}",
        plot_filename,
        stim_info=stim_info,
        config=config
    )

    print(f"Extracted onsets:\n{extracted_onsets}")
    print("-------------------------------------------------")

    # Display plot
    plt.figure(figsize=(14, 12))
    img = mpimg.imread(plot_filename)
    plt.imshow(img)
    plt.axis("off")
    plt.tight_layout()
    plt.show()

    return output, extracted_onsets, stats


def make_json_safe(obj):
    """Recursively convert NumPy types to Python-native types."""
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(x) for x in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj

def run_repp_batch(
    base_output_dir,
    config,
    participant_filter=None,
    node_filter=None
):
    """
    Batch REPP analysis with enriched JSON output.
    Saves:
      /analysis_plots/<participant>/<trial>_plot.png
      /analysis_json/<participant>/<trial>_analysis.json
    """

    global_plot_dir = os.path.join(base_output_dir, "analysis_plots")
    global_json_dir = os.path.join(base_output_dir, "analysis_json")

    os.makedirs(global_plot_dir, exist_ok=True)
    os.makedirs(global_json_dir, exist_ok=True)

    # Loop over participants
    for participant_id in os.listdir(base_output_dir):

        participant_dir = os.path.join(base_output_dir, participant_id)
        if not os.path.isdir(participant_dir):
            continue

        # Apply participant filter
        if participant_filter and participant_id != participant_filter:
            continue

        # Create participant-specific output dirs
        participant_plot_dir = os.path.join(global_plot_dir, participant_id)
        participant_json_dir = os.path.join(global_json_dir, participant_id)

        os.makedirs(participant_plot_dir, exist_ok=True)
        os.makedirs(participant_json_dir, exist_ok=True)

        print(f"\n=== Processing {participant_id} ===")

        wav_files = [f for f in os.listdir(participant_dir) if f.endswith(".wav")]
        json_files = [f for f in os.listdir(participant_dir) if f.endswith("_stim_info.json")]

        for wav in wav_files:
            base_name = wav[:-4]

            # Apply node filter
            if node_filter and not wav.startswith(node_filter):
                continue

            # Find JSON
            json_name = base_name + "_stim_info.json"
            if json_name not in json_files:
                print(f"❗ Missing JSON for {wav}")
                continue

            wav_path = os.path.join(participant_dir, wav)
            json_path = os.path.join(participant_dir, json_name)

            # Output plot + JSON paths
            plot_filename = os.path.join(participant_plot_dir, base_name + "_plot.png")
            enriched_json_filename = os.path.join(
                participant_json_dir, base_name + "_analysis.json"
            )

            # Load raw stim info
            with open(json_path, "r") as f:
                stim_info = json.load(f)

            print("------------------------------------------")
            print(f"Analyzing: {wav}")
            print(f"Stim info: {json_path}")
            print(f"Saves -> plot: {plot_filename}")
            print(f"Saves -> analysis JSON: {enriched_json_filename}")
            print("------------------------------------------")

            try:
                output, analysis, is_failed = do_beat_detection_analysis(
                    wav_path,
                    title_plot=base_name,
                    output_plot=plot_filename,
                    stim_info=stim_info,
                    config=config
                )

                # Build enriched JSON

                enriched = {
                    "stim_info_original": stim_info,
                    "output_signal_processing": {
                        #"resp_onsets_detected": output.get("resp_onsets_detected", []),
                        #"resp_onsets_aligned": output.get("resp_onsets_aligned", []),
                        "markers_onsets_input": output.get("markers_onsets_input", []),
                        "markers_onsets_detected": output.get("markers_onsets_detected", []),
                        "markers_onsets_aligned": output.get("markers_onsets_aligned", []),
                        "num_resp_raw_onsets": output.get("num_resp_raw_onsets", 0)
                    },
                    "analysis_statistics": analysis,
                    "failure_checks": is_failed
                }

                # Convert all NumPy types to JSON-safe types
                enriched_safe = make_json_safe(enriched)

                # Save JSON (overwrite if it exists)
                with open(enriched_json_filename, "w") as jf:
                    json.dump(enriched_safe, jf, indent=4)

                print(f"✔ Done {base_name}")

            except Exception as e:
                print(f"❌ Error in {base_name}: {e}")
                continue

    print("\n🎉 All analyses complete!")




import os
import json
import shutil
import re

def run_repp_batch_failed(
    base_output_dir,
    config,
    participant_filter=None,
    node_filter=None
):
    """
    Robust REPP batch analysis + improved logging and reliable saving.

    - All failed trial files are saved into:
        base_output_dir/failed_trials/
    - Filenames use participant from the participant folder (never None),
      and try to include node and trial parsed from the wav filename.
    - Counters only increment after successful saves (WAV + JSON).
    - Prints clear diagnostics when saves fail or PNG is missing.
    """

    failed_dir = os.path.join(base_output_dir, "failed_trials")
    os.makedirs(failed_dir, exist_ok=True)

    # Counters
    total_trials = 0
    total_passed = 0
    total_failed_detected = 0        # number of trials flagged failed by analysis
    total_failed_saved = 0           # number of failed trials successfully saved (wav+json)
    participants_processed = 0

    print("\n============================================")
    print("🟦 Starting REPP Batch Analysis")
    print("============================================\n")

    def parse_base_name_parts(base_name, participant_id):
        """
        Return (participant, node, trial_id)
        - participant: taken from participant_id (folder) ALWAYS.
        - node, trial_id: try to parse from base_name using patterns;
          if not found, fall back to 'unknown_node' and base_name as trial.
        """
        # Remove any existing 'participant_' prefix from base_name to avoid duplication
        base_name = re.sub(r'^participant_\d+__?', '', base_name)

        # default values
        participant = participant_id
        node = None
        trial = None

        parts = base_name.split("__")

        # Find node and trial number (only first occurrence)
        for p in parts:
            if p.startswith("node_") and node is None:
                node = p.split("node_", 1)[1]
            elif p.startswith("trial_") and trial is None:
                trial = p.split("trial_", 1)[1]

        # Optionally, append remaining parts as trial descriptor
        remaining = [p for p in parts if not p.startswith("node_") and not p.startswith("trial_")]
        if remaining:
            trial = f"{trial}__{'__'.join(remaining)}"

        # Fallbacks if nothing found
        if node is None:
            node = "unknown_node"
        if trial is None:
            trial = base_name

        return participant, node, trial

    for participant_id in os.listdir(base_output_dir):

        participant_dir = os.path.join(base_output_dir, participant_id)
        if not os.path.isdir(participant_dir):
            continue

        # Participant filter
        if participant_filter and participant_id != participant_filter:
            continue

        participants_processed += 1

        print(f"\n=== 👤 Processing participant: {participant_id} ===")

        wav_files = [f for f in os.listdir(participant_dir) if f.endswith(".wav")]
        json_files = [f for f in os.listdir(participant_dir)
                      if f.endswith("_stim_info.json")]

        if not wav_files:
            print("⚠ No WAV files found for this participant — skipping.")
            continue

        participant_passed = 0
        participant_failed_detected = 0
        participant_failed_saved = 0

        for wav in wav_files:
            base_name = wav[:-4]
            total_trials += 1

            # Node filter (string prefix check like original implementation)
            if node_filter and not wav.startswith(node_filter):
                print(f"⏭ Skipping {wav} (node filter does not match)")
                continue

            json_name = base_name + "_stim_info.json"
            if json_name not in json_files:
                print(f"❗ Missing JSON for {wav} → skipping analysis for this file")
                continue

            wav_path = os.path.join(participant_dir, wav)
            json_path = os.path.join(participant_dir, json_name)

            # Temp plot path (do_beat_detection_analysis is expected to create this)
            temp_plot_path = os.path.join(participant_dir, base_name + "_temp_plot.png")

            # Load stim info
            with open(json_path, "r") as f:
                stim_info = json.load(f)

            print("------------------------------------------")
            print(f"🎧 Analyzing: {wav}")
            print("------------------------------------------")

            try:
                output, analysis, is_failed = do_beat_detection_analysis(
                    wav_path,
                    title_plot=base_name,
                    output_plot=temp_plot_path,
                    stim_info=stim_info,
                    config=config
                )

                # Build enriched json
                enriched = {
                    "stim_info_original": stim_info,
                    "output_signal_processing": {
                        "markers_onsets_input": output.get("markers_onsets_input", []),
                        "markers_onsets_detected": output.get("markers_onsets_detected", []),
                        "markers_onsets_aligned": output.get("markers_onsets_aligned", []),
                        "num_resp_raw_onsets": output.get("num_resp_raw_onsets", 0)
                    },
                    "analysis_statistics": analysis,
                    "failure_checks": is_failed
                }

                enriched_safe = make_json_safe(enriched)

                # If analysis says failed:
                if is_failed.get("failed", False):
                    total_failed_detected += 1
                    participant_failed_detected += 1

                    # Parse final names, using folder participant_id as canonical participant
                    participant_val, node_val, trial_val = parse_base_name_parts(base_name, participant_id)

                    final_base = f"{participant_val}__node_{node_val}__trial_{trial_val}"

                    print(f"⚠ FAILED (detected) → candidate filename: {final_base}")

                    # Attempt to save: WAV + JSON first (must succeed to consider it 'saved')
                    wav_saved = False
                    json_saved = False
                    png_saved = False

                    # target filepaths in the single failed folder
                    out_wav = os.path.join(failed_dir, final_base + ".wav")
                    out_json = os.path.join(failed_dir, final_base + ".json")
                    out_png = os.path.join(failed_dir, final_base + ".png")

                    # Copy WAV
                    try:
                        shutil.copy2(wav_path, out_wav)
                        wav_saved = True
                    except Exception as e_copy:
                        print(f"❌ Failed to copy WAV to {out_wav}: {e_copy}")

                    # Save enriched JSON
                    try:
                        with open(out_json, "w") as jf:
                            json.dump(enriched_safe, jf, indent=4)
                        json_saved = True
                    except Exception as e_json:
                        print(f"❌ Failed to write JSON to {out_json}: {e_json}")

                    # Move PNG if it exists
                    if os.path.exists(temp_plot_path):
                        try:
                            shutil.move(temp_plot_path, out_png)
                            png_saved = True
                        except Exception as e_png:
                            print(f"❌ Failed to move PNG {temp_plot_path} -> {out_png}: {e_png}")
                    else:
                        print(f"ℹ PNG not found at expected temp location: {temp_plot_path} (PNG skipped)")

                    # Decide whether we count this as "saved"
                    if wav_saved and json_saved:
                        total_failed_saved += 1
                        participant_failed_saved += 1
                        print(f"✅ FAILED TRIAL SAVED: {final_base} (wav+json{', +png' if png_saved else ''})")
                    else:
                        print(f"⚠ FAILED TRIAL NOT FULLY SAVED: {final_base} (wav_saved={wav_saved}, json_saved={json_saved}, png_saved={png_saved})")

                else:
                    participant_passed += 1
                    total_passed += 1
                    print(f"✔ PASSED → {base_name}")

                    # cleanup temp PNG if present
                    if os.path.exists(temp_plot_path):
                        try:
                            os.remove(temp_plot_path)
                        except Exception:
                            pass

            except Exception as e:
                print(f"❌ ERROR processing {base_name}: {e}")
                # remove temp_plot if left over
                if os.path.exists(temp_plot_path):
                    try:
                        os.remove(temp_plot_path)
                    except Exception:
                        pass
                continue

        # Participant summary
        print(f"\n📊 Participant summary for {participant_id}:")
        print(f"   ➤ Passed (saved/recognized): {participant_passed}")
        print(f"   ➤ Failed (detected): {participant_failed_detected}")
        print(f"   ➤ Failed (saved - wav+json): {participant_failed_saved}")
        print("------------------------------------------")

    # Global summary
    print("\n============================================")
    print("🟩 BATCH ANALYSIS COMPLETE")
    print("============================================")
    print(f"Participants processed: {participants_processed}")
    print(f"Total trials examined: {total_trials}")
    print(f"Total passed: {total_passed}")
    print(f"Total failed (detected by analysis): {total_failed_detected}")
    print(f"Total failed (successfully saved wav+json): {total_failed_saved}")

    if total_trials == 0:
        print("⚠ No trials found. Check your base_output_dir path or filters.")

    if total_failed_detected == 0:
        print("✨ No failed trials detected!")

    print("============================================\n")
