use near_sdk::{env, near, require, AccountId, NearToken, PanicOnDefault, Promise};
use near_sdk::collections::LookupMap;
use near_sdk::json_types::{U128, U64};

const VERSION: &str = "decision-lab-commitment-registry.v1";

#[near(serializers = [borsh, json])]
#[derive(Clone)]
pub struct Record {
    pub commitment: String,
    pub signer_id: AccountId,
    pub block_height: U64,
    pub block_timestamp_ns: U64,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Registry {
    records: LookupMap<String, Record>,
    count: u64,
}

#[near]
impl Registry {
    #[init]
    pub fn new() -> Self {
        Self { records: LookupMap::new(b"c"), count: 0 }
    }

    pub fn contract_version(&self) -> String { VERSION.to_string() }
    pub fn get_count(&self) -> U64 { U64(self.count) }
    pub fn storage_cost_per_byte(&self) -> U128 { U128(env::storage_byte_cost().as_yoctonear()) }

    pub fn get_commitment(&self, commitment: String) -> Option<Record> {
        valid_commitment(&commitment);
        self.records.get(&commitment)
    }

    /// First registration is immutable. Only the salted commitment is supplied;
    /// runtime provenance records the public submitter, not proven authorship.
    #[payable]
    pub fn register_commitment(&mut self, commitment: String) -> Record {
        valid_commitment(&commitment);
        let attached = env::attached_deposit();
        if let Some(record) = self.records.get(&commitment) {
            refund(attached);
            return record;
        }
        let initial_storage = env::storage_usage();
        let record = Record {
            commitment: commitment.clone(),
            signer_id: env::predecessor_account_id(),
            block_height: U64(env::block_height()),
            block_timestamp_ns: U64(env::block_timestamp()),
        };
        self.records.insert(&commitment, &record);
        let required = NearToken::from_yoctonear(
            u128::from(env::storage_usage() - initial_storage) * env::storage_byte_cost().as_yoctonear()
        );
        require!(attached >= required, "Attached deposit must cover record storage");
        self.count = self.count.checked_add(1).expect("Registry count overflow");
        refund(attached.saturating_sub(required));
        record
    }
}

fn valid_commitment(value: &str) {
    require!(value.len() == 64 && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)),
        "Commitment must be 64 lowercase hexadecimal characters");
}

fn refund(amount: NearToken) {
    if !amount.is_zero() {
        Promise::new(env::predecessor_account_id()).transfer(amount).detach();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use near_sdk::{test_utils::{VMContextBuilder, get_created_receipts}, testing_env};

    fn context(account: &str, deposit: u128, height: u64) {
        let mut builder = VMContextBuilder::new();
        builder.current_account_id("registry.testnet".parse().unwrap())
            .predecessor_account_id(account.parse().unwrap())
            .signer_account_id(account.parse().unwrap())
            .attached_deposit(NearToken::from_yoctonear(deposit))
            .account_balance(NearToken::from_near(10))
            .block_height(height).block_timestamp(height * 1_000_000_000);
        testing_env!(builder.build());
    }

    #[test]
    fn registration_records_runtime_provenance_and_refunds_storage_surplus() {
        context("alice.testnet", 10u128.pow(22), 100);
        let mut registry = Registry::new();
        let record = registry.register_commitment("a".repeat(64));
        assert_eq!(record.signer_id.as_str(), "alice.testnet");
        assert_eq!(record.block_height.0, 100);
        assert_eq!(record.block_timestamp_ns.0, 100_000_000_000);
        assert_eq!(registry.get_count().0, 1);
        assert_eq!(registry.contract_version(), VERSION);
        assert!(!get_created_receipts().is_empty());
        let encoded = near_sdk::serde_json::to_value(&record).unwrap();
        assert!(encoded["block_timestamp_ns"].is_string());
        assert_eq!(encoded.as_object().unwrap().len(), 4);
        assert!(registry.get_commitment("b".repeat(64)).is_none());
    }

    #[test]
    fn duplicate_never_overwrites_first_submitter_or_timestamp() {
        context("alice.testnet", 10u128.pow(22), 100);
        let mut registry = Registry::new();
        registry.register_commitment("a".repeat(64));
        context("bob.testnet", 10u128.pow(22), 200);
        let record = registry.register_commitment("a".repeat(64));
        assert_eq!(record.signer_id.as_str(), "alice.testnet");
        assert_eq!(record.block_height.0, 100);
        assert_eq!(registry.get_count().0, 1);
        assert!(!get_created_receipts().is_empty());
    }

    #[test]
    #[should_panic(expected = "Attached deposit must cover record storage")]
    fn storage_is_funded_by_the_new_record_submitter() {
        context("alice.testnet", 0, 100);
        Registry::new().register_commitment("a".repeat(64));
    }

    #[test]
    #[should_panic(expected = "Commitment must be 64 lowercase hexadecimal characters")]
    fn malformed_commitments_are_rejected() {
        context("alice.testnet", 10u128.pow(22), 100);
        Registry::new().register_commitment("A".repeat(64));
    }
}
