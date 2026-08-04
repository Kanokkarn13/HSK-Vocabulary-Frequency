from etl.batch_gate import should_process_batch


def test_first_batch_processes_even_without_changes():
    assert should_process_batch(
        wordlist_changed=False,
        extraction_states=[{"changed_source_count": 0}],
        production_exists=False,
    )


def test_no_change_skips_existing_production():
    assert not should_process_batch(
        wordlist_changed=False,
        extraction_states=[{"changed_source_count": 0}, {"changed_source_count": 0}],
        production_exists=True,
    )


def test_new_source_processes_existing_production():
    assert should_process_batch(
        wordlist_changed=False,
        extraction_states=[{"changed_source_count": 1}],
        production_exists=True,
    )


def test_force_processes_existing_unchanged_production():
    assert should_process_batch(
        wordlist_changed=False,
        extraction_states=[],
        production_exists=True,
        force=True,
    )
