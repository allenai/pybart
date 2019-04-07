from main import main


def test():
    out = main("blackbox.conllu")
    print(out)
    print("------------- TESTS ---------------------------------------------------------------------------\n")
    out_lines = out.split('\n')
    i = 0
    test_name = ""
    last_failed_test = ""
    failed_tests = 0
    test_count = 0
    for gold_line in open("expected_blackbox_output.conllu", 'r').readlines():
        if gold_line.startswith('#'):
            if gold_line.split(":")[0] == "# test":
                test_name = gold_line.split(":")[1].strip()
                test_count += 1
            continue
        if gold_line.startswith('\n'):
            i += 1
            continue
        
        if out_lines[i].split() != gold_line.split():
            print("test %s failed:\n\tgold:\t%s\n\toutput:\t%s\n" % (test_name, gold_line.split(), out_lines[i].split()))
            if test_name != last_failed_test:
                failed_tests += 1
                last_failed_test = test_name
        i += 1
    
    if failed_tests > 0:
        print("\x1b[1m\033[91mPassed tests: %d/%d\033[0m\x1b[21m" % (test_count - failed_tests, test_count))
    else:
        print("\x1b[1m\033[94mGreat success: %d/%d!!!\033[0m\x1b[21m" % (test_count - failed_tests, test_count))


if __name__ == "__main__":
    test()
