# split_file.py
def split_file(input_file, num_chunks=4):
    with open(input_file, "r") as f:
        data = f.read()

    size = len(data)
    chunk_size = size // num_chunks

    for i in range(num_chunks):
        start = i * chunk_size
        end = (i + 1) * chunk_size if i < num_chunks - 1 else size
        chunk_data = data[start:end]

        with open(f"worker/data/chunk{i+1}.txt", "w") as out:
            out.write(chunk_data)

if __name__ == "__main__":
    split_file("sample_file.txt", 4)
