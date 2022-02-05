from time import sleep

print("This is my file to demonstrate best practices.")

def process_data(data):
    print("Beginning data processing...")
    modified_data = data + " that has been modified"
    sleep(1)
    print("Data processing finished.")
    return modified_data


if __name__ == "__main__":
    print(process_data("abcdef from main file"))
